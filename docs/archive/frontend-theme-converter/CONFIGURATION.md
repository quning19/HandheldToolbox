# 配置规范

## 生效顺序

脚本相对工程根目录解析 `config/project.json`，批次通过 `theme_profile` 选择 `config/themes/*.json`。`source/` 是输入，`lab/` 保存实验文件，`dist/staged/` 保存增量产物，`dist/themes/` 保存完整主题，`dist/_reports/` 保存报告。

## project.json

### paths

所有路径都是相对工程根目录的路径：

- `platform_config`：两个转换工具共用的平台配置
- `system_config`：最终完整平台 XML 基线（与RP6当前版本一致）
- `reference_system_config`：ES-DE 官方平台配置
- `themes`：完整主题输出根目录
- `reports`：报告目录
- `lab`：实验目录

### theme_naming

- `source` 固定为 `capabilities_xml`，表示从源主题的 `<themeName>` 读取基础名。
- `fallback_base` 是缺少或无法读取 `<themeName>` 时的基础名。
- 天马 G 后缀 `_天马G` 属于转换器固定规则，不是可配置字段。

## theme profile

每种主题拥有独立的 `source_theme`、`staged`、`metadata_dir` 和槽位定义。当前已登记 `alekfull-nx`、`aura`、`canvas`、`elementerial`、`iconic`、`iisu`、`playstation-x` 七个 profile。没有按系统存放的元数据 XML 时，`metadata_dir` 为 `null`。

### slots

槽位名映射到主题内相对目录。未在 `slot_ext` 声明的槽位默认使用 `.webp`；同一目录可以按不同扩展名定义多个槽位，例如 Aura 的 `logo-svg` 与 `logo-webp`。

- `required_slots`：目标平台、母体或显式回退平台至少有一个可用资源，否则预检和构建失败。
- `badge_slots`：从母体或显式回退平台取用的栅格图在这些槽位叠加当前药丸标记；目标平台本身已有的资源原样复制。Alekfull NX、Iconic 的 `carousel`，Iconic 的各 `*-overlay`，PlayStation-X 的 `overlays`，Aura 的 system-logo 和 Elementerial 的 logo 都直接复制。
- 未列入 `required_slots` 且所有候选平台都没有资源的槽位保持缺省，不生成文件。
- `slot_ext`：按槽位指定非默认扩展名，例如 PlayStation-X 的 `logos` 使用 `.svg`、`videos` 使用 `.mp4`。
- `directory_slots`：Aura 的 `default-art` 按系统分目录。条目列出每个系统的文件名后缀；构建时逐张优先查找目标资源，再回退母体资源，并改写平台文件名前缀。
- `copy_only_suffixes`：Aura 的 `default-art` 基础图供 carousel/grid 使用，不叠加标记；其他插画变体按 `badge_slots` 处理。
- `metadata_copy_dirs`：可选的额外 XML 目录。Elementerial 在 `metadata-global` 之外还复制 `metadata-custom`；只修改已有的 `<systemName>`。

`config/badge_params.json` 的 `active_candidate` 选择正式构建使用的标记方案。当前为 `P_pill_top_right`，药丸高度 `min(0.065 ×（长边＋半个短边）＋15, 140)` 像素，黑底不透明度 170。`default` 保留旧版实验参数。

## batch JSON

批次根字段 `theme_profile` 选择主题结构 profile。每个 `platforms` 条目保存：

- `name`：已验证的系统名，用于关联共用平台配置。
- `vendor`：厂商分类。
- `action`：当前批次意图，允许 `new`、`alias`、`patch`，用于说明和审计。
- `slots`：`all` 表示主题 profile 的全部槽位，否则填写槽位名数组。
- `fallback_source`：可选的主题特有第二回退资源名。
- `note`：人类可读的变更原因。

`theme`、`source`、`badge_text`、`system_name` 由共用平台配置加载，不再在各批次重复维护。加载器检查冲突，不允许批次偷偷改写共用平台规则。`badge_text` 为 `null` 时不加文字，`system_name` 为 `null` 时不生成新的主题元数据 XML；具体槽位与布局仍由主题 profile 决定。

## 第一批处理约定

- 资源查找顺序固定为：目标平台名（`theme`）→ 母体名（`source`）→ 显式回退名（`fallback_source`）。目标平台资源存在时原样复制，不覆盖成母体版本。PlayStation-X 的 `nesh` 因而保留已有的专用资源，只从 `nes` 回退缺失的槽位。
- 从回退平台取用的栅格图仅在对应槽位属于 `badge_slots` 且设置了 `badge_text` 时绘制标记；未列入 `badge_slots` 的槽位和目标平台已有的栅格图直接复制。栅格输出沿用该槽位扩展名，支持 WebP、JPEG 和 PNG。
- SVG 和视频槽位直接复制并改名，不进行压暗、文字或格式转换。
- 完整主题打包时，若同一元数据目录有 `androidgames.xml` 和 `switch.xml`，将 Android games 的 `systemCoverSize` 与 `systemCartSize` 改成 Switch 的值；原版 `source/` 不修改。
- 需要生成 XML 时，按相同候选顺序选取已有 XML；都没有时尝试 `_default.xml`。输出复制源文本，仅替换或插入 `<systemName>`。`system_name` 或 `metadata_dir` 为 `null` 时不生成主 XML；额外 XML 目录没有候选源文件时也不生成。
- 不做 XML 描述中文化，不做主题布局或集合系统转换。
- 不生成 `WII` 大写资源；天马 G 配置系统标识使用小写 `wii`，ROM 路径仍可为 `%ROMPATH%/WII`。
- 图片、SVG、视频资源名在预检、构建和槽位校验中按目录真实文件名精确匹配。XML 读取和校验目前使用文件系统的存在性判断，在 Windows 上尚未保证大小写精确匹配。

## 共用平台配置

平台定义与识别已抽到[platforms.json](../../FrontendTransTool/retrolibx/src/frontend_platforms/platforms.json)（路径按工程根目录说明）。通过project.paths.platform_config指定位置，Python 3.9可直接加载旁边的frontend_platforms模块。76个系统定义来自本项目已验证的custom_systems-PG/es_systems.xml；Wii标识wii与目录WII、GBA HACK与目录/主题GBA hack均保留。九个平台的母体、角标和显示名也已抽出，七个批次仅保留平台选择、槽位与主题特有处理。system_config所在的custom_systems-PG目录是最终完整配置基线，四个XML不得按主题批次或游戏选择裁剪。2026-10-12只读比较确认与RP6逐字节一致。此次没有重建或改动主题素材和dist产物。

2026-10-12 后续统一：platforms.json 已改为 version 2，只维护别名、母体、类型和角标，不再重复存储 ROM 目录、主题、扩展名或启动命令。platform_registry 明确从 project.paths.system_config 所在目录读取完整四文件，与游戏转换使用同一 XML 定义。主题素材、排序 XML 及已有 dist 产物未修改；本次仅做静态 review，未执行测试或构建。
