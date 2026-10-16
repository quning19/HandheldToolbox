# 天马G与Android ES-DE

模型、输入输出目录及合并/排序边界见 [业务说明](PROJECT_GUIDE.md)。本文介绍保留的 retrolibx.cli Android 命令；其普通 convert 与 Android build 共用列表合并和基线保护，但不生成完整 Android 配置及任务脚本。独立 library_converter 的 Windows 业务会自动处理完整平台配置，不能混用这两个入口的说明。

基于RetroLibX 0.1.0上游提交f1a73c126ba450ae7d01a856e17ed7aad83eeff9，保留MIT许可及现有架构。使用Python 3.12+，依赖由uv.lock固定。ROM留在原目录，只原样复制封面、Logo、视频三类素材（JPEG 使用 .jpg 后缀），不导出mini、不缩放、不转码。

## 本地输入

在仓库根目录运行，先按实际目录准备 examples/retrolibx/profile.local.json 的工作副本：

```powershell
& '.\retrolibx\.venv\Scripts\python.exe' -m retrolibx.cli scan --config examples/retrolibx/profile.local.json
& '.\retrolibx\.venv\Scripts\python.exe' -m retrolibx.cli build --config examples/retrolibx/profile.local.json --platform GBA --out jobs/gba
```

--platform可重复，不填写则拒绝生成；平台名是源metadata所在的相对目录，子平台独立选择。build只写新的任务目录，不写源资源或正式ES-DE。已有任务目录不自动覆盖。上游detect/scan/convert/inspect/validate继续保留。

多个平台直接放入同一个`build`命令，输出一个`apply.sh`、一份完整平台配置及各平台gamelist，不再逐平台生成后拼接。例如`--platform GBA --platform GB`。没有专门的“全平台自动发现并修复”步骤，所选范围仍由调用方明确给出。

--platform只限定游戏列表和媒体范围，files/custom_systems始终输出完整平台配置：es_systems.xml连同es_find_rules.xml、es_import_rules.xml、es_systems_sorting.xml完整保留。基线为本项目src/frontend_platforms/custom_systems-PG；旧RP6对照是历史记录，不表示当前用户配置与其逐字相同。有启动阻塞时仍输出完整配置预览，只不生成apply.sh。

source_root是电脑目录或设备索引目录；device_rom_root是掌机实际源ROM根目录；esde_root是掌机ES-DE目录。路径字段相对配置文件定位。source_profile可指定来源规则JSON，默认使用天马G规则；原引擎普通convert默认generic，处理天马包时明确使用--source-profile，详见[来源规则](SOURCE_PROFILES.md)。target_snapshot是现有ES-DE配置副本；首次目标确实为空才能显式使用target_empty。platform_config_dir可指定完整四文件XML目录，识别和配置生成共用该来源，缺失时报错。默认读取frontend_platforms包内的完整基线，不再读取相邻主题工程。media_root可选，必须与捕获的ES-DE MediaDirectory一致；首版支持绝对媒体目录，未解析的变量/相对路径报错。

默认使用从旧主题工程迁入本项目的[共用平台配置](PLATFORMS.md)：内部平台与系统名使用GBA HACK，ROM目录和主题使用GBA hack，VIB使用GBA vib；Wii保留系统名wii与目录WII。systems_template可省略，也可明确指定外部模板。system_ids只指定输出系统名，不改变内部平台；现有系统ROM路径唯一匹配时优先复用现有标识、主题与启动命令，有重叠或多个匹配则停止。支持ES-DE原生settings/es_settings.xml及旧根目录设置布局；读取并核对原始字节哈希，不改写设置。

## 游戏子目录封面

ES-DE 按文件或文件夹在平台内的相对路径查找媒体，不读取 `gamelist.xml` 中的 `<image>` 标签。子目录不会自动沿用内部游戏的图片。转换时为含有现存 ROM 和有效封面的子目录补充独立封面，使用内部游戏的原封面，不缩放、不拼图。

例如 `GBA hack/合集/game.zip` 的游戏封面位于 `<媒体目录>/<系统名>/covers/合集/game.png`，文件夹封面则位于 `<媒体目录>/<系统名>/covers/合集.png`。嵌套目录逐级补齐，目录名里的点和中文完整保留。优先采用直属游戏的封面；没有直属候选时采用较近的后代游戏，相同层级按 ROM 相对路径固定选择。没有可用游戏封面的目录不生成图片。

文件夹封面只增加媒体复制项，不增加游戏、改变文件夹进入行为或修改来源 metadata。图片目标与已有游戏媒体计划冲突时保留游戏图片并发出警告；其他已有目标文件沿用所选冲突策略。共用模式仍按游戏绑定更新来源引用，文件夹副本包含在同一来源图片的副本检查中。

命名和查找规则依据 [ES-DE 媒体说明](https://gitlab.com/es-de/emulationstation-de/-/blob/master/USERGUIDE.md#manually-copying-game-media-files)及[官方 FileData 实现](https://gitlab.com/es-de/emulationstation-de/-/blob/master/es-app/src/FileData.cpp)。主题决定使用的图片类型；现有 Canvas 的网格采用 cover，或包含 cover 的回退顺序。

## 设备输入

旧列表的绝对 ROM 根目录与当前来源目录不同时，配置 `gamelist_rom_roots`，按输出系统名明确列出允许的旧根。例如 `{"psx": ["/storage/实际卡号/Roms/psx"]}` 可将旧绝对路径归一成当前 PS1 系统的相对路径；未声明的其他根仍拒绝合并。旧列表系统目录名与当前配置不同，可用 `gamelist_sources` 明确指定来源，例如 `{"nes": "famicom", "megadrive": "genesis", "sfc": "snes"}`。仅在当前目标列表不存在时读取该旧列表，保留收藏、统计和额外记录；发布基线仍以当前目标文件是否存在为准，旧列表不删除。这些选项只改变本地转换，需按实际捕获资料填写，不采用任意根或模糊匹配。这些选项的测试范围以 STATUS 中具体批次为准，不据历史说明推断已全量回归。

明确需要沿用另一平台的启动与主题时，用`system_templates`指定内部平台/输出ID到模板ID的映射。例如PSP Minis使用`"system_ids": {"psp-minis": "pspminis"}`和`"system_templates": {"psp-minis": "psp"}`；优先读取快照中的PSP节点，缺失时读取完整基线。不再为这一映射临时复制并修改一份XML模板。已有所选节点保持位置及ROM路径写法，未选择的节点保留。

设备需通过adb devices -l显示为device。capture只取所选metadata、目录/大小索引和目标XML，不取ROM、图片或视频正文：

```text
retrolibx capture --adb <adb.exe> --serial <授权序列号> --source-root <掌机ROM根目录> --esde-root <掌机ES-DE目录> --platform GBA --out jobs/catalog
retrolibx build --config jobs/catalog/config.json --platform GBA --out jobs/gba
```

catalog里的ROM/媒体是零字节占位文件，仅用于索引；实际大小保存在device-index.json。不能把catalog当真实ROM包，也不能对它使用普通convert复制媒体。生成任务使用索引定位资源，设备脚本直接复制掌机原文件，普通复制没有额外的逐文件存在/大小检查。

## 执行

生成 gamelist、拷贝媒体与资源异常检查分别列任务、分别授权。正常执行读取所需 metadata、解析路径并记录命令结果；没有专项检查授权时，不主动盘点 metadata 引用是否对应实际 ROM、孤立/重复/缺失资源或全库完整性，也不主动扩展旧数据兼容排查。需要这些检查时，先提出独立的范围和必要性。正常执行自然发现问题，报告具体异常及受影响项；受阻项保留失败状态，其他独立且已授权的项可继续。排查、筛除记录、修改捕获副本、补规则和修复后重建均另列任务，不顺带执行。程序现有解析和发布基线约束保持生效，内置约束不构成额外人工专项检查授权。计划和计时分别标明生成、拷贝、发布、检查、修复及测试。

先看preview.md与summary.json。有缺ROM、冲突或缺启动映射时不生成apply.sh。plan.json用于核查，不提供手工修改后重新执行的入口。

设备脚本只创建媒体目录并复制所选文件。只需将 `apply.sh` 单独上传到掌机；其余预览、计划、发布清单及 XML 留在电脑端。`upload` 默认只显示本地上传清单，不连接设备；审核后加 `--apply` 才上传：

```text
retrolibx upload jobs/gba/apply.sh --adb <adb.exe> --serial <授权序列号> --remote /storage/emulated/0/Download/task-gba/apply.sh
retrolibx upload jobs/gba/apply.sh --adb <adb.exe> --serial <授权序列号> --remote /storage/emulated/0/Download/task-gba/apply.sh --apply
```

完整目录采用 C2：先创建完整目标目录，再执行 `adb push <本地目录>/. <完整目标目录>/`。`/.` 保留为字符串后缀，不能通过 `Path / "."` 拼接后被规范化掉。单文件采用 C4：先创建目标父目录，再把最后一个参数明确写成目标文件全名。路径保持 Unicode 字符串，ADB 使用参数列表调用，shell 路径使用 POSIX 引号。禁止把中文来源直接推送到已有父目录并依赖 ADB 自动取名。

目录上传会复制所选目录的全部文件，保留设备额外文件，不执行删除或 `apply.sh`；单文件上传仅复制该文件。筛选、增量及跳过已有文件应保持逐文件 C4，不得改为上传整个来源目录。当前 `upload` 入口不提供筛选或增量比较。上传失败可能留下部分文件，不自动清理；返回成功表示 ADB 已完成传输，文件内容与目录清单仍须按获批范围核对。

退出ES-DE后，在有目录权限的终端运行任务脚本：

```sh
sh /storage/emulated/0/Download/task-gba/apply.sh
```

脚本只含 `set -e`、一个 `mkdir -p` 和逐文件 `cp -n`。命令失败即停止，`-n` 保留已有媒体；不做大小、哈希、临时文件或恢复状态处理。脚本不依赖 XML payload，不发布 gamelist 或平台配置，不更新原 metadata，也不删除源素材。

媒体脚本成功完成并经用户验收后，电脑端通过普通 ADB 命令发布 XML。`publication.json` 记录基线、payload 和可选共用迁移，留在本地；`publish` 默认只预览，不连接设备、不自动运行复制脚本。普通模式不重复检查 ROM 和全部素材，先复制后发布的步骤由操作顺序和逐步验收保证。平台配置已单独处理时使用 `--skip-platform-config`，只发布游戏列表（共用开启时还包含原 metadata）：

```text
retrolibx publish jobs/gba --adb <adb.exe> --serial <授权序列号> --skip-platform-config
retrolibx publish jobs/gba --adb <adb.exe> --serial <授权序列号> --skip-platform-config --apply
```

电脑端保留 XML 基线保护，避免覆盖生成任务后新增的收藏、统计等用户数据。通过 `adb shell cp` 保留旧 XML 备份，C4 `adb push` 上传到完整临时文件名，核对该 XML 的哈希后通过 `adb shell mv` 发布；不自动运行媒体脚本。目标已经等于待发布内容时跳过。gamelist按ROM路径补空字段和新增条目，保留已有名字、简介、收藏、统计、altemulator及其他条目；XML 外部变化后重新capture/build。省略 `--skip-platform-config` 才将任务中有变化的平台 XML 纳入发布范围，完整四文件预览始终保留。

普通复制中断可能留下不完整的目标文件；`cp -n` 不会覆盖该文件，不能将重跑成功当作内容验收。发生复制失败时报告当次文件，另行批准替换该文件，不在脚本中引入恢复流程。ADB shell权限不等于其他终端应用权限。

### 电脑端统一部署

`deploy`复用C4上传及`publish`，默认仅在本地预览，不连接设备。批准所列全部步骤后加`--apply`；需要逐步批准时选择`--stage upload`、`copy`或`publish`，只执行该步。

```text
retrolibx deploy jobs/task --adb <adb.exe> --serial <授权序列号> --remote /storage/emulated/0/Download/task/apply.sh --skip-platform-config
retrolibx deploy jobs/task --adb <adb.exe> --serial <授权序列号> --remote /storage/emulated/0/Download/task/apply.sh --skip-platform-config --apply
```

仅上传`apply.sh`。设备内复制仍只执行最小脚本，XML备份和发布通过电脑端普通ADB；共用开启时继续使用原有副本核对和源metadata发布逻辑。普通模式不加全库匹配、媒体哈希或异常修复。脚本必须为仓库生成的UTF-8/LF格式，格式异常直接报告，不在部署时修复。执行阶段的开始/结束、耗时、失败原因及结果保存在本地`deployment-result.json`，短报为`deployment-brief.md`；同一任务分步调用保留已有阶段记录，失败后不自动执行后续步骤或修复重跑。这些记录是命令执行结果，不代表专项资源检查或游戏启动验收。

天马来源规则默认要求在confirmed_systems列出GBA vib（或明确映射的输出系统名），实际设备确认启动方案后填写。否则只出预览。确认后保留完整现有/基线命令及选项顺序，不强制核心文件名含gpsp_rumble，也不强制launch_overrides；确需覆盖命令时才提供该项。来源规则的confirmation_systems名单可以按实际资源包调整。

用户明确选择metadata启动配置时，可配置`"metadata_launch_systems": ["GBA vib"]`，该选项同时表达启动确认。转换只支持本次实际使用的`am start --user 0 -n <包/组件> -e <键> <值> --activity-clear-top`形式，将ROM参数映射为`%ROMRAW%`并保留核心、配置路径及标志；只转换文本，不执行来源命令。未支持的参数报错，不猜测或丢弃；不与同一平台的`launch_overrides`同时使用。其他平台不自动采用metadata启动配置。

## 检查与交付状态

当前实现、各批获批检查范围和待验收事项集中在[STATUS.md](STATUS.md)。此前真实节选和MuMu复制、哈希及中断恢复记录保存在[历史实现记录](../archive/implementation/2026-10-12-before-cleanup.md)，不代表拆分后的新版已完成设备验收。

设备界面、实际启动、VIB震动和终端权限由用户验收。同文件多个collection、变量或相对媒体根当前明确报错；通用Pegasus回导不保证原文注释、编码或排版。默认不原地修改源资源，可选共用迁移使用原metadata局部字节补丁。

工作区整理已清理旧构建包，尚未重新打包。测试、构建与设备写入均需按用户明确批准的范围执行。

## 可选共用素材迁移

`shared_pegasus` 默认 false。明确配置 `"shared_pegasus": true` 后，媒体脚本仍只复制封面、Logo、视频。随后电脑端 `publish` 通过普通 ADB 命令核对所有源素材和副本 SHA-256，通过后才备份并局部更新掌机原 `Roms/<平台>/metadata.pegasus.txt`；全部 metadata 发布且目标再次核对成功后才清理计划内、未被其他字段引用的源素材。摘要保存在电脑任务目录 `shared-media-hashes.json`，用于同任务发布/清理重试，不上传设备。原ROM引用、启动、排序、描述、注释、编码及换行保持；mini不移动。build本身只生成任务和预览，不修改电脑输入或设备。任务中的 `preview/source-metadata/` 提供可读预览，`files/source-metadata/` 的Base64文件由电脑端解码后上传，保留原字节。详见 [SHARED_MEDIA.md](SHARED_MEDIA.md)。新版设备发布尚未联调验收，本地测试范围见 [STATUS](STATUS.md)。
