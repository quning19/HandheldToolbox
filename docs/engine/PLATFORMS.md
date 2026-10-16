# 统一平台定义

完整 XML 的唯一维护位置是 [custom_systems-PG](../../src/frontend_platforms/custom_systems-PG)，包括 es_systems.xml、es_find_rules.xml、es_import_rules.xml、es_systems_sorting.xml。此基线从原主题工程迁入，保留原 76 系统与命令、顺序。新设备初始化完整四文件；已有设备保留原节点及启动参数，补齐本次所需平台。不再读取相邻 FrontendThemeConverter。

[platforms.json](../../src/frontend_platforms/platforms.json) version 2 仅保存别名、母体、类型、角标和主题显示名等补充信息；目录、主题及命令来自 XML。`frontend_platforms` 的标准库识别和用户配置模块兼容 Python 3.9；生成 XML 的 catalog.py 复用项目引擎及 lxml，要求项目 Python 3.12 环境。

工作目录 config/platforms.json 是另一种“用户覆盖”文档，schema version 2：保存默认表快照、用户字段覆盖、用户新增及明确禁用。内部 ID 稳定，用户改过字段优先，未改字段采用新默认，新平台自动加入；冲突保留用户项并提示。被移除但仍使用的旧默认保留并提示停止维护。删除不删除 ROM、媒体或设备配置。

旧 schema version 1 全列表使用随包 baseline-v1.json 迁移，先验证并在 backups/config 保留原字节；缺少对应基线时保留全部现有字段，不推断删除意图。迁移不需要用户重新录入。

主题模式“沿用母体”直接使用母体 theme，不生成额外主题资源；“独立分类”使用自己的 theme 和可选角标。游戏库与主题工具共同读取这些定义，GUI 不持有另一份业务模型。

GBA HACK 是内部系统名，GBA hack 是 ROM 目录和主题名；GBA vib、Wii 的 wii/WII 以及用户 PSP Minis 定义均保持已有约定。旧工具的批次配置仅用于开发回归对照，见 tools/themes/config，不参与通用主题解析的运行时分派。
