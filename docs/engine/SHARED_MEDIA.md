# ES-DE 素材与天马G共用

共用素材默认关闭。普通转换和 Android build 都只导出封面、Logo、视频；明确开启共用后，将原天马G素材迁入 ES-DE 的媒体布局，并直接更新正在使用的原metadata，不再生成独立Pegasus副本。

## 开关与范围

| 入口 | 默认 | 开启方式 |
| --- | --- | --- |
| 普通 convert | 关闭；只复制，源metadata和媒体不变 | `--shared-pegasus --rom-mode none` |
| Android build | `shared_pegasus: false`；任务只发布ES-DE | 配置 `"shared_pegasus": true` |

Android仍只处理明确选中的平台，平台内全部游戏按匹配结果补充三类素材引用；全库迁移需明确选择全部平台。补找采用来源规则中明确的目录优先级及同级首选，并报告多个候选；没有候选或状态未知时，不修改其原引用。默认不开启时不产生原metadata更新或源媒体清理计划。

| Pegasus字段 | ES-DE目录 | 天马补找名 |
| --- | --- | --- |
| box_front | covers | boxfront / box_front / boxart2d |
| logo | marquees | logo / wheel |
| video | videos | video |

原ROM相对目录保留，目标按每个ROM文件名去扩展名命名。图片支持PNG/JPG/JPEG/WebP，视频支持MP4/MKV/AVI/WMV/MOV/WebM；JPEG使用.jpg后缀，字节不转码、不缩放。显式有效引用优先，缺失或失效时按来源profile补找；ES-DE／SaveDeck 的天马来源共用按目录优先级选择的规则，同级多个候选选排序后的第一个并报告，generic默认不补找。补找候选扩展名沿用 PegasusGGameManager（视频不包含 WMV），完整规则见 [SOURCE_PROFILES.md](SOURCE_PROFILES.md#媒体)。

mini、背面、截图、标题画面、背景、卡带/光盘、manual、music等不迁移；原文件夹不整体删除。被其他素材字段、collection默认素材或其他metadata引用的源文件继续保留并报告，避免产生失效引用。

## 执行顺序

1. 核对ROM、原metadata摘要、源素材和所有已有目标；共用模式使用SHA-256核对内容，不能只按文件存在或大小判断一致。
2. 完成所有素材副本。一条游戏多ROM时，ES-DE仍需要逐ROM副本；天马该游戏引用第一份ROM对应的素材。
3. 所有目标副本核对成功后，发布ES-DE配置，备份并局部更新原metadata的三类素材路径。Android 流程的副本核对、发布由电脑端通过普通 ADB 命令完成，设备脚本只创建目录和拷贝文件。
4. 再次确认metadata已发布和目标副本一致，仅清理本计划中允许迁移的源文件。Android 流程由电脑端控制 ADB 删除，媒体脚本不删除源素材。

原metadata不通过通用模型重新渲染。按源记录位置替换已有素材路径或补充缺少的assets字段；ROM、启动、排序、开发者、描述、扩展字段、注释、编码/BOM和原换行保留。原metadata变化会停止执行。每个基线备份为 `metadata.pegasus.txt.frontendtrans.<原SHA-256>.bak`，保留原字节。多行素材路径无法安全局部修改时明确报错。

多个文件发布不构成全库原子事务。失败时不进入后续清理；中断可能留下已复制目标或已更新的部分metadata，原素材保留到全部metadata发布后。清理阶段中断可能保留部分重复源文件；同一Android任务保存运行时素材摘要，重试时核对已发布内容。不要改动任务中的payload或摘要记录。

关闭开关不自动恢复迁移前的布局。恢复原metadata和素材属于单独操作；只恢复metadata备份会让已清理的旧素材引用失效。

## 普通转换

在本项目根目录使用本地真实资源，先替换路径。下面只是原引擎命令示例，本次未执行：

```powershell
& '.\retrolibx\.venv\Scripts\python.exe' -m retrolibx.cli convert 'D:/实际ROM根目录' --from pegasus --to es-de --output 'D:/实际ES-DE目录' --source-profile src/retrolibx/profiles/pegasus-g.json --rom-mode none --shared-pegasus --dry-run
```

`--dry-run`只生成可审阅的计划，包括 `write_source_metadata` 和 `migrate_source_media`，不写目标、不改来源。实际执行此开关会更新电脑上的原metadata并清理对应原媒体；来源和输出目录不能重叠，ROM必须为none，媒体必须为copy，拒绝rename。

引用始终指向本次实际输出的downloaded_media。已移除旧 `--pegasus-media-base` 参数，不能只改引用为掌机路径却复制到电脑目录。电脑源资源需要映射到掌机时使用Android build。已有目标内容不同，默认skip模式会停止迁移；普通转换只有明确采用overwrite才允许替换，不会跳过不同内容后删除来源。

## Android任务

配置保持 `"shared_pegasus": false` 或省略此字段即关闭。开启时，媒体引用依据实际MediaDirectory，原metadata位置依据device_rom_root；不重写ROM引用，不更改game_dirs.txt，不依赖额外扫描目录。

build只写新任务目录，不修改电脑输入或掌机。任务包含：

- `summary.json`：shared_pegasus、source_metadata_updates、source_media_cleanup、shared_media_checks。
- `preview/source-metadata/<平台>/metadata.pegasus.txt.preview.txt`：UTF-8可读预览，供审阅；不作为部署文件。
- `files/source-metadata/<平台>/metadata.pegasus.txt.b64`：Base64保存原编码及换行的待发布字节。
- `plan.json`：完整操作计划，仅留在本地核查。
- `apply.sh`：最小设备复制脚本，仅 `set -e`、`mkdir -p`、`cp -n`，不检查大小或哈希，不发布 metadata，不删除源素材；设备只需上传此脚本。
- `publication.json`：电脑端 ADB 发布及源媒体清理清单，XML/metadata payload 均留在本地；`publish` 默认预览，加 `--apply` 才执行，平台 XML 可通过 `--skip-platform-config` 排除。

设备索引的媒体占位文件不作为素材正文使用。复制脚本不计算或保存摘要。仅共用模式的电脑端 `publish` 在修改原 metadata 前，通过 ADB 读取真实源素材和所有副本的 SHA-256，核对设置及 metadata 基线。摘要留在电脑任务目录 `shared-media-hashes.json`；所有目标必须与源摘要一致。发布完成后再次核对所有 metadata 和媒体目标，再通过普通 ADB 命令清理所选源素材。源素材清理中断后使用同一电脑任务重试 `publish`，不需要重跑复制脚本。已有目标内容不同会在发布前停止，不自动覆盖。构建使用电脑真实资源时还会记录来源摘要，掌机资源须与其一致。普通非共用模式不执行这些迁移检查。

默认内部存储示例为 `/storage/emulated/0/ES-DE/downloaded_media`；实际路径由用户配置和ES-DE设置决定，不能沿用历史卡号。ROM、mini和其他资源不移动。设备执行须另有用户授权，当前实施没有部署或执行此任务。

## 记录与检查状态

2026-10-13通过ADB只读盘点，GT78_VN内置ES-DE媒体目录的10个平台仅有covers、marquees、videos，文件数分别为2495、2495、2245。按用户决定撤回额外五类逻辑，并将旧Pegasus副本方案替换为上述默认关闭的迁移方案。

新增及调整用例涵盖三类范围、多ROM副本、原字节/编码/换行保留、默认关闭、只读规划、变化停止、复制失败、目标冲突、其他字段仍引用来源和Android任务阶段。2026-10-13按用户批准执行15个本地用例：首轮12通过、3失败，修正CRLF测试预期后复测失败3项，2通过、1失败；修复多ROM重新生成计划时误判已迁移素材越界的问题后，仅复测该项，通过。15项均有通过记录，未在最后修复后整文件重跑。详见[测试摘要](../../jobs/shared-media-test-summary-20261013.json)。未连接ADB、未执行掌机脚本、未修改真实资源或设备；未做全量回归、构建、lint、类型检查或覆盖率。
