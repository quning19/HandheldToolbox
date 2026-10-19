> 历史快照：2026-10-16 文档整理时从 `docs/engine/PROJECT_GUIDE.md` 归档。原文中的当前状态、待办、路径和测试结论只代表原记录阶段；不构成现在的操作授权。当前事实见 [STATUS](../../STATUS.md)。

# 当前数据、平台与目录说明

记录日期：2026-10-12。本文描述当前源码的实际行为；建议及处理状态见 [静态 review](../../REVIEW-2026-10-12.md)，尚未实施的建议不属于已完成功能。后续已按用户授权统一平台来源、列表合并及天马来源规则。用户批准的五个平台/合并用例及三个来源规则用例全部通过，全部使用本地临时数据；未运行全量回归、覆盖率、lint、类型检查、构建或设备测试。

## 1. “合并已有列表”具体做什么

Android `build` 从 `target_snapshot/gamelists/<输出系统名>/gamelist.xml` 读取旧列表；普通 `convert --to es-de` 从输出目录的同一路径读取旧列表。两者使用同一个合并函数，以 **ROM 相对平台目录的路径** 匹配游戏，例如 `./子目录/游戏.zip`，不是以显示名称匹配。位于该平台 ROM 根目录内的绝对路径会归一化到相同的匹配键，包括本地 Windows 绝对路径。

| 情况 | 当前处理 |
|---|---|
| ROM 已在旧列表中，字段有非空值 | 保留旧值，即使新源值不同 |
| ROM 已在旧列表中，字段缺失或文本为空 | 用新列表补齐 |
| 新增 ROM | 追加新条目 |
| 旧列表的其他游戏、文件夹或额外 XML 字段 | 保留，不因本次没有导出而删除 |
| 相同路径重复、路径越界 | 报错，不猜测应合并哪条 |
| ROM 改名或移动到另一个相对路径 | 作为新记录，旧记录仍保留，不自动转移统计 |

例如，旧条目有 `favorite=true`、`playcount=12`、`lastplayed=...`、`altemulator=...` 或用户增加的 XML 标签，新导出仍保留这些非空字段。旧 `favorite=false` 也会保留，不会被源中的 `true` 覆盖。已有 `name`、`desc` 和 `sortname` 同样优先保留，因此源侧修改简介或排序不会自动覆盖用户现有值。

这不是汇总两份游玩记录；不相加次数、不选取最近日期，也不保证原 XML 的空白、编码和排版逐字节不变。实现见 [merge.py](../../../../src/retrolibx/adapters/esde/merge.py)。

**适用边界：** 两个 ES-DE 入口均以保留用户字段的方式更新列表，生成原文件哈希保护并保留 `.frontendtrans.bak`；媒体和 ROM 仍按所选冲突策略处理。普通 `convert` 不自动生成 Android 完整系统配置，`--dry-run` 只生成合并计划、不写目标。复制 ROM 时匹配根是输出的 `ROMs/<平台目录>`；不复制时依据实际 ROM 及其相对路径确定源根，多个不同根时报错，不猜测。没有旧列表快照或旧目标列表时，没有可保留的历史记录。不要把设备索引的零字节文件作为普通 `convert` 的媒体输入。

“保留已有 ES-DE 统计”与“从天马导入统计”也不同：当前 Pegasus 导入会读取 `favorite`，没有把源 `hidden`、`playcount`、`lastplayed` 转成模型中的相应字段；原始源字段会保存在 `source_metadata`，但不因此自动出现在新的 ES-DE XML 中。模型没有独立 `playtime` 字段，旧 XML 中的该字段仍能由上述合并保留。

## 2. 排序和其他信息保留范围

| 信息 | 当前行为及边界 |
|---|---|
| 游戏级 `sort` / `sort-by` | 转为 `Game.sort_name`，写入 ES-DE `sortname`；两者同时存在时 `sort` 优先 |
| 新建列表的条目顺序 | 按输入游戏顺序、每个游戏的 ROM 顺序展开；合并时旧条目位置保留，新条目追加 |
| 一个游戏多个 ROM | 展开为多个条目，显示名使用各 ROM 文件名去掉扩展名，排序值共用；没有生成版本间的独立排序键 |
| 平台级 collection `sort-by` | 留在平台原始元数据，未转为 ES-DE 平台排序；使用完整 `es_systems_sorting.xml` 中的现有顺序 |
| 已有 ES-DE `sortname` | 非空旧值优先，不随源 `sort-by` 自动更新 |
| 名称、简介、开发者、发行商、类型、日期、人数、评分、收藏 | 有模型及目标字段映射；普通 Pegasus 保持开发者原义，天马来源配置可启用版本说明规范化，不能称作逐字原样保留 |
| 任意源自定义字段 | 原始信息保存在模型，未全部映射为 ES-DE 字段 |
| 媒体 | 当前 ES-DE 只导出封面、Logo、视频三类素材；目录与角色见 [SHARED_MEDIA.md](../../SHARED_MEDIA.md)。不导出 mini，不缩放、不转码，其他素材不导出 |

真实节选中的“口袋妖怪 红宝石”有 4 个 ROM，游戏 `sort-by: 007`，展开后的 4 个条目都写 `sortname=007`。这保留了与其他游戏的排序键，不能保证相同键下 ES-DE 界面的版本显示顺序。

GBA collection 的源 `sort-by: 018` 没有覆盖完整配置中的平台顺序；现有配置的 `gba`、`GBA HACK`、`GBA vib` 分别使用 `0020`、`0021`、`0022`。ES-DE 实际界面排序、主题显示和启动效果由用户验收，此处只说明文件内容及代码逻辑。

## 3. 平台定义的位置和维护关系

| 内容 | 当前路径与作用 |
|---|---|
| 最终完整 XML 基线 | `src/frontend_platforms/custom_systems-PG/`，含 4 个文件、76 个系统；2026-10-12 已有只读对比记录表明四文件与 RP6 完全一致 |
| 本项目发布用 XML 副本 | [src/frontend_platforms/custom_systems-PG/](../../../../src/frontend_platforms/custom_systems-PG)，独立安装且主题工程不在声明路径时使用；不作为另一份手工维护定义 |
| 独立平台识别及主题补充配置 | [src/frontend_platforms/platforms.json](../../../../src/frontend_platforms/platforms.json)，version 2，只含配置来源路径、别名、母体、明确的 hack/vib 类型、角标及主题显示名；目录、主题、扩展名和命令在运行时从 XML 读取 |
| 平台加载、识别与主题规则 | [src/frontend_platforms/__init__.py](../../../../src/frontend_platforms/__init__.py)，两项目共用，不靠名称含 `hack` 就猜测平台 |
| 上游其他前端映射 | [src/retrolibx/registry/systems.yaml](../../../../src/retrolibx/registry/systems.yaml)，为其他目标适配器保留；本项目共用平台定义优先 |
| 主题工具接入位置 | `FrontendThemeConverter/config/project.json` 的 `paths.platform_config` 指向上述 JSON，`paths.system_config` 指向最终 XML |

四个 XML 分别为 `es_systems.xml`（系统、ROM 路径、扩展名、启动命令、主题等）、`es_find_rules.xml`（模拟器查找规则）、`es_import_rules.xml`（导入规则）、`es_systems_sorting.xml`（系统排序等元数据）。文件在本次只导出一个平台时仍完整保留，不按游戏选择裁成单平台。

| 内部平台 ID / 默认 ES-DE 系统名 | 源 ROM 目录 | 主题名 | 母体 / 类型 |
|---|---|---|---|
| `gba` | `GBA` | `gba` | 普通 GBA |
| `GBA HACK` | `GBA hack` | `GBA hack` | `gba` / `hack` |
| `GBA vib` | `GBA vib` | `GBA vib` | `gba` / `vib` |
| `wii` | `WII` | `wii` | 普通 Wii |

不用 `gbah`、`gbavib` 另建内部命名。系统名、目录名、主题名是三个不同字段，不能相互推导；例如 `MD hack` 与 `MD hack(picodrive)` 是明确独立的平台。`system_ids` 只指定输出系统名，不改内部平台 ID；发现现有系统的 ROM 路径唯一匹配时，会优先复用该系统标识、主题与命令。

**维护方式：** 本地两个工程读取主题工具的 XML 基线；JSON 不再重复维护 XML 字段。默认 XML 目录及独立安装的发布副本目录在 JSON 中明确声明，主目录不存在时才使用发布副本；主目录部分文件缺失会报错。显式 `platform_config_dir` 缺失也直接报错，不回退到其他配置。发布副本需在发布时从基线更新，不做双向同步。更多识别说明见 [PLATFORMS.md](../../PLATFORMS.md)。

## 4. 通用数据模型是什么

定义位于 [core/models.py](../../../../src/retrolibx/core/models.py)。模型使用 Pydantic，运行时主要驻留内存；不是另建一份游戏数据库，也不是把每种前端都改成 ES-DE 字段。

```text
Library                         一次导入的整个库
├─ format / source_path         源格式、电脑上的源根目录
├─ systems[]                    平台
│  └─ System
│     ├─ id / name / short_name / platform_ids
│     ├─ metadata               源平台目录、原 collection 字段、输出映射等
│     └─ games[]
│        └─ Game                一条源游戏，可对应多个 ROM
│           ├─ id / name / sort_name
│           ├─ description / developer / publisher / genre[] / release_date
│           ├─ players_min / players_max / rating
│           ├─ favorite / hidden / play_count / last_played
│           ├─ roms[]           每项有 path、name、size、hash、disc、metadata
│           ├─ media            封面、截图、Logo、视频、手册等独立角色
│           ├─ launch           emulator、core、command、working_directory、args
│           └─ source_metadata  未完全标准化的原始字段，按源格式保存
├─ collections[]                跨游戏集合结构；当前天马导入未填充这一层
├─ metadata
└─ diagnostics[]                提示、警告、错误及关联平台/游戏/路径
```

模型提供字段不等于每个输入和输出适配器都已支持该字段。例如 Pegasus 当前主要保存原 `launch.command`，没有把所有 Android 命令解析成标准的 `emulator/core/args`；多个 collection 在同一 metadata 文件中目前明确不支持。Game ID 可以为空，尚未建立跨路径重命名后的持久身份。

下面按真实红宝石节选展示关键结构，**是省略字段的说明例子，未在本次运行程序重新导出**。`<本地源根>` 代表电脑绝对路径；完整模型中简介、原始字段及其他默认字段也存在。

```json
{
  "format": "pegasus",
  "source_path": "<本地源根>/Roms",
  "systems": [{
    "id": "gba",
    "name": "Nintendo Game Boy Advance",
    "metadata": {
      "source_platform": "GBA"
    },
    "games": [{
      "name": "口袋妖怪 红宝石",
      "sort_name": "007",
      "roms": [
        {"path": "<本地源根>/Roms/GBA/口袋妖怪 红宝石 [1]386版汉化.zip"},
        {"path": "<本地源根>/Roms/GBA/口袋妖怪 红宝石 [2]J版官译全汉化.zip"},
        {"path": "<本地源根>/Roms/GBA/口袋妖怪 红宝石 [3]E版官译全汉化.zip"},
        {"path": "<本地源根>/Roms/GBA/口袋妖怪 红宝石 [4]E版官译全汉化+英文名+可联动+可银行.zip"}
      ],
      "media": {
        "box_front": "<本地源根>/Roms/GBA/media/口袋妖怪 红宝石/boxfront.png",
        "logo": "<本地源根>/Roms/GBA/media/口袋妖怪 红宝石/logo.png",
        "video": "<本地源根>/Roms/GBA/media/口袋妖怪 红宝石/video.mp4"
      },
      "launch": {"command": "继承 GBA collection 的原始 launch 命令"},
      "source_metadata": {"pegasus_fields": "原始 game/file/sort-by/assets 等字段"}
    }]
  }]
}
```

一条 Game 共用一组媒体，ES-DE 导出时再展开为 4 个 ROM 条目及各自的 3 个媒体目标。其他目标可以保留一条游戏多 ROM 的关系，无需先把源模型压平成 ES-DE 列表。

`scan --json` 可显示模型序列化；`plan.json` 是文件操作计划，不是游戏库模型。两者用途不同。设备 capture 的 `path` 指向电脑上的零字节占位文件，实际设备路径和大小由配置、`device-index.json` 提供，不能误认为占位文件就是 ROM 内容。

## 5. 输入、输出、配置目录

### 5.1 当前 RP6 的源目录与 ES-DE 目标

以下来自已有只读目录和配置记录；本次没有操作掌机。

```text
/storage/<SD_VOLUME>/Roms/                 device_rom_root，卷标已脱敏，原始 ROM 不搬迁
├─ GBA/
│  ├─ metadata.pegasus.txt                 游戏和 collection 元数据
│  ├─ 游戏.zip                            可以包含多版本
│  ├─ 子目录/游戏.zip                      保留相对目录
│  └─ media/游戏名/
│     ├─ boxfront.png 或其他图片扩展名
│     ├─ logo.png
│     ├─ video.mp4
│     └─ mini_boxfront.* / mini_logo.*     源资源；当前不导出
├─ GBA hack/                              与 GBA 平级，包含嵌套 ROM 目录
├─ GBA vib/                               与 GBA 平级
└─ 其他平台/

/storage/emulated/0/ES-DE/                esde_root
├─ custom_systems/                       始终使用完整平台配置
│  ├─ es_systems.xml
│  ├─ es_find_rules.xml
│  ├─ es_import_rules.xml
│  └─ es_systems_sorting.xml
├─ gamelists/<输出系统名>/gamelist.xml     系统名不是 ROM 目录名
├─ downloaded_media/<输出系统名>/         实际媒体根受设置控制
│  ├─ covers/<ROM相对路径去扩展名>.<图片扩展名>
│  ├─ marquees/<ROM相对路径去扩展名>.<图片扩展名>
│  └─ videos/<ROM相对路径去扩展名>.<视频扩展名>
└─ settings/es_settings.xml               只读 MediaDirectory，不由转换器改写
```

例如 ROM 为 `GBA hack/系列/游戏.zip`，媒体目标保留 `covers/系列/游戏.png`。源媒体按游戏名称集中存放，目标媒体按 ROM 相对路径命名，两者本来就不是相同结构。

RP6 现有 Hack 的物理列表/媒体目录记录为 `GBA hack`，系统配置 `<name>` 是 `GBA HACK`；不要仅凭大小写就另建一个平台。默认配置保持主题工具命名，build 可复用捕获的现有系统标识。

当前 RP6 的 `MediaDirectory` 为空，使用默认 `ES-DE/downloaded_media`；若捕获设置中是自定义绝对目录，构建读取该值，不能擅自假设默认目录。当前未支持解析变量或相对媒体根。

### 5.2 本地真实输入、设备索引与任务包

```text
FrontendTransTool/test_data/original_excerpt/
├─ Roms/{GBA,GBA hack,GBA vib}/           真实 ROM、metadata、媒体正文
├─ expected.json                         样本预期说明
├─ manifest.json                         原始样本清单
└─ output/                               历史导出，可能使用旧命名，非最新配置基线

<capture输出目录>/                       设备只读采集的本地目录结构
├─ config.json                           相对本目录的 build 配置
├─ device-index.json                     原始设备文件大小/路径索引
├─ Roms/<所选平台>/
│  ├─ metadata.pegasus.txt                正文
│  ├─ 游戏.zip                           零字节占位，未下载 ROM
│  └─ media/...                          零字节占位，未下载媒体
└─ snapshot/                             作为 target_snapshot
   ├─ custom_systems/                    捕获的完整平台 XML
   ├─ gamelists/<现有系统>/gamelist.xml    当前 capture 采集目标现有 XML，不只所选源平台
   └─ settings/es_settings.xml           现有设置，若存在

<build输出目录>/                         可检查的 Android 任务包
├─ preview.md                            文本概要，非界面截图
├─ summary.json                          统计、问题、executable
├─ files/
│  ├─ gamelists/<所选输出系统>/gamelist.xml
│  └─ custom_systems/                    四个完整配置文件
├─ apply.sh                              仅 mkdir 与 cp；需另行授权设备写入
├─ publication.json                      电脑端 ADB 发布清单，留在本地
├─ plan.json                             没有阻塞问题时才生成；操作计划
└─ .retrolibx/manifest.json               本地执行器生成的清单
```

任务包不内置 ROM 和媒体正文。设备脚本的媒体源是 `device_rom_root` 下的原文件；ROM 仍在原目录。产生任务包本身不代表已经应用到掌机。

共用素材默认关闭。开启时另有 `files/source-metadata/<平台>/metadata.pegasus.txt.b64` 和 `preview/source-metadata/`。设备脚本只创建目录和复制素材；共用模式的电脑端 `publish` 再通过普通 ADB 命令核对副本、备份、更新原metadata及清理源素材，摘要保存在电脑端供同任务重试；不生成另一份待扫描的Pegasus列表。普通复制不重复检查 ROM、媒体大小和哈希。设备只需上传 `apply.sh`，其余任务记录、XML及metadata payload 留在电脑端。详见 [SHARED_MEDIA.md](../../SHARED_MEDIA.md)。

已有 [jobs/rp6-complete-config-20261012/](../../../../jobs/rp6-complete-config-20261012) 中，`custom_systems/` 是可查看的完整四文件产物，`rp6-snapshot/` 是四文件平铺的只读对比副本，`comparison.json` 是对比记录。该平铺副本不是上述完整 `snapshot/` 目录，不能直接当作包含现有列表及设置的 build 快照。这个产物也不是整库游戏及媒体的完整导出。

### 5.3 普通本地 convert 的输出

```text
<convert输出目录>/
├─ gamelists/<系统名>/gamelist.xml
├─ downloaded_media/<系统名>/{covers,marquees,videos}/...
├─ ROMs/<平台ROM目录>/...                 仅选择复制 ROM 时出现
└─ .retrolibx/manifest.json
```

项目的 Android build 固定不复制 ROM。上游普通 convert 的默认 ROM 模式是复制，必须按用途明确选择；它共用已有列表合并流程，但不生成 Android build 的完整平台配置。普通目录复制已经足够，项目不采用符号链接导出。

### 5.4 配置文件与可选字段

当前 [examples/profile.local.json](../../../examples/profile.local.json) 指向真实节选及 **MuMu 的独立测试目录**，不是 RP6 的正式配置，不能照搬其 `device_rom_root/esde_root/target_empty` 到正式设备。

| HandheldConfig 字段 | 内容 |
|---|---|
| `source_root` | 电脑真实输入目录或 capture 的 `Roms` 索引目录，必填 |
| `device_rom_root` | 掌机实际源 ROM 根目录，必填 |
| `esde_root` | 掌机目标 ES-DE 根目录，必填 |
| `target_snapshot` | 电脑上现有 ES-DE XML 的快照，用于合并及基线保护 |
| `target_empty` | 确认目标确实为空；不能借此忽略已有目标数据 |
| `encoding` | 源 metadata 编码，默认 `utf-8-sig` |
| `source_profile` | 可选来源规则 JSON；Android 默认天马G规则，普通命令默认 generic，可用 `--source-profile` 指定 |
| `platform_config_dir` | 可选完整四文件 XML 基线目录；平台路径使用 `%ROMPATH%/<目录>`，识别和系统配置输出同时读取此处，缺失时报错；不是设备目标快照 |
| `device_index` | capture 文件大小索引；真实本地输入可省略 |
| `systems_template` | 外部 es_systems 模板，覆盖完整默认配置中的相应系统，非裁剪列表 |
| `system_templates` | 明确指定平台采用哪个现有/基线节点作为模板，例如PSP Minis使用psp；省去临时复制XML |
| `metadata_launch_systems` | 明确指定采用metadata启动配置的平台，同时表达启动确认；仅转换已支持的Android命令形式 |
| `media_root` | 可选媒体根，必须与快照设置的 MediaDirectory 一致 |
| `shared_pegasus` | 默认 false；明确开启后，核对三类目标素材、局部更新掌机原metadata，再清理对应源素材；build本身不操作设备 |
| `system_ids` | 内部平台 ID → 输出系统名，不改变内部数据平台 |
| `launch_overrides` | 指定平台的 ES-DE 完整启动命令覆盖，非 ROM 或媒体转换规则 |
| `confirmed_systems` | 已确认特殊核心映射的系统；当前主要用于 VIB 检查 |

电脑路径相对配置文件所在目录解析；Android 路径应明确写真实绝对路径。平台选择由 `build --platform` 参数提供，不是向完整平台配置删条目。普通 convert 对应提供 `--platform-config-dir`；省略时与本地默认配置一样读取主题工具基线，独立安装环境使用声明的发布副本。

### 5.5 两个工程的资源与输出位置

```text
D:\Game Tools\HandheldTools\FrontendTransTool/
├─ retrolibx/                            实际 Git 代码仓库
│  ├─ src/frontend_platforms/            共用平台配置、识别模块、四文件副本
│  ├─ src/retrolibx/
│  │  ├─ adapters/                       各输入/输出格式适配器
│  │  ├─ core/                           通用模型、计划、执行器
│  │  ├─ profiles/                       普通 Pegasus 与天马G来源规则 JSON
│  │  ├─ application/                    通用转换、设备采集、Android任务编排
│  │  └─ registry/                       上游跨前端平台映射
│  ├─ examples/                          本地配置例子
│  ├─ docs/                              当前说明及review状态；archive/保存历史
│  ├─ tests/                             测试源码，执行需单独批准
│  ├─ .venv/                             本地运行环境
│  └─ assets/                            保留的上游标识素材
├─ test_data/                            真实节选、样本清单、研究与历史输入/输出
├─ jobs/                                 任务包、导出、设备只读快照及报告
├─ references/{tools,apks}/               原参考工具、APK，不是产品代码
├─ docs/                                 已确认方案、实现记录、资源清单
│  └─ archive/                           旧 superpowers 方案与历史资料
└─ .deps/                                本地工具及研究依赖，不是导出产物

D:\Game Tools\HandheldTools\FrontendThemeConverter/
├─ source/
│  ├─ configs/custom_systems-PG/         最终完整 XML 基线
│  ├─ configs/custom_systems-es-de/       官方配置对照
│  ├─ themes/                            原主题输入
│  └─ sample/                            参考主题
├─ config/
│  ├─ project.json                       路径、共用平台入口、输出命名
│  ├─ themes/*.json                      各主题槽位与布局
│  ├─ batches/*.json                     批次选择与主题动作，共用平台信息加载时补齐
│  └─ badge_params.json                  角标视觉参数
├─ tools/                                主题处理工具
├─ dist/
│  ├─ staged/<主题profile>/              增量中间产物
│  ├─ themes/<themeName>_天马G/           完整可部署主题
│  └─ _reports/                          处理报告
├─ lab/                                  实验材料
└─ tests/                                主题测试源码
```

主题布局、槽位及角标绘制属于主题工程；平台识别、母体及平台命名共用。主题输出不会被游戏转换自动重新生成。历史 jobs 和 test_data/output 可能反映之前的两平台配置或旧 ID，判断当前能力应看源码和本次完整配置基线，不能把所有旧产物都当成最新版本。

## 6. 需要抽配置的内容

平台维护来源和两个入口的列表合并已统一；天马媒体目录约定、版本说明及 VIB 确认也已抽成 [来源规则](../../SOURCE_PROFILES.md)。获批八个用例通过。按用户决定，排序暂不调整。

输入/输出根目录、设备 ROM 根、媒体根、编码、完整平台 XML 目录、平台别名输出和启动覆盖已经有配置，不需要再造一套复杂配置系统。ES-DE 固定目录名、metadata 文件名、XML 格式及安全检查可以留在代码里。原 review 证据及后续处理状态见 [REVIEW-2026-10-12.md](../../REVIEW-2026-10-12.md)。

## 7. VIB 预览与核心映射

`GBA vib` 是主题工具已有的独立平台分类。实际源样本引用 `gpsp_rumble_libretro_android.so`；完整 ES-DE 配置中该节点的首个 gpSP 命令引用 `gpsp_libretro_android.so`，此外保留其他核心/模拟器选项。来源规则不通过这些文件名推断实际功能。

“核心映射”指：把源的模拟器/核心选择与参数对应到 ES-DE 的启动命令，关系到是否保持用户想要的震动行为；不会转换 ROM、改变媒体，也不是创建一个名叫 VIB 的新引擎。仅凭文件名不同，不能断言用户已测试的 RP6 配置不可用。

“VIB 预览”是生成 `preview.md`、`summary.json`、游戏列表及完整平台 XML 供检查，不是运行 ES-DE 界面或游戏。天马规则的 `confirmation_systems` 默认包含 `GBA vib`；未确认时 `executable=false`，不生成 `apply.sh/plan.json`，但完整 VIB 配置节点和列表预览仍保留。

确认后沿用用户已有/基线的完整启动命令，不再强制特定核心文件名或覆盖命令。来源配置可明确指定需要确认的平台。视觉、实际游戏启动及震动效果继续由用户验收。详情见 [SOURCE_PROFILES.md](../../SOURCE_PROFILES.md)。

## ES-DE 职责归并补充（2026-10-13）

PegasusGGameManager 的旧 export-esde 已退役，ES-DE 列表与封面、Logo、视频三类素材统一在此维护。按用户决定，已撤回额外五类素材导出和默认补找；上游原有通用媒体字段仍保留。共用素材默认关闭，已按用户确认替换原Pegasus副本方案：复用媒体绑定和计划，先复制并核对所有目标，按原metadata记录位置局部改三类素材引用，备份发布后再清理对应来源。ROM和其他字段保持，mini及仍被其他字段引用的源素材保留。普通 convert 的 --shared-pegasus 与 Android shared_pegasus 配置见 [SHARED_MEDIA.md](../../SHARED_MEDIA.md)。本次15个本地用例已分别取得通过记录，首轮失败项修复后定向复测；未做全量回归、真实资源或设备执行，详见 [STATUS.md](../../STATUS.md)。
