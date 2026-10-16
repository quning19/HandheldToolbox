# 发布数据与资源边界

更新日期：2026-10-16。本表区分计划随 Windows 独立版发布的数据、运行时动态资料和仅开发使用的资料；当前尚未生成独立 EXE。目录职责见 [结构](ARCHITECTURE.md)，清理规则见 [工作目录](WORKSPACE_DATA.md)。

| 资源编号 | 数据或文件 | 是否随独立版发布 | 作用与更新方式 |
|---|---|---|---|
| R01 | Python 业务/GUI、运行环境与所需依赖 | 需要；具体打包方式待定 | 提供扫描、转换、设备通信和界面；随软件版本更新，当前开发虚拟环境不直接作为发布包 |
| R02 | frontend_platforms/custom_systems-PG 四个 XML | 需要 | 新设备完整初始化、已有配置补齐及启动模板来源；随软件维护基线，保留用户现有节点和启动参数 |
| R03 | platforms.json、baseline-v1.json | 需要 | 默认别名、母体、主题表现及旧配置迁移依据；新版默认与用户新增/覆盖/禁用合并，不覆盖用户整表 |
| R04 | retrolibx/profiles 与 registry 数据 | 需要 | 天马来源约定、媒体补找、版本说明、确认名单和其他前端映射；随软件版本更新 |
| R05 | theme_converter 通用解析、素材策略与角标参数 | 需要 | 解析实际主题并生成资源；无完整主题和逐主题运行配置，规则变化参与结果过期判断 |
| R06 | 四套平台卡片图与来源/许可记录 | 计划附带，独立分发前确认条件 | 832 张、40,732,940 字节（约 38.8 MiB）；随版本更新，设置切换仅改变本地展示 |
| R07 | frontend_gui/assets/app/app.ico | 需要 | 选定的竖版 1，多尺寸应用图标；随软件版本更新，改版前保留原稿 |
| R08 | settings.json | 不预置用户文件；运行后生成于程序同级 | 记录唯一工作目录、亮暗模式、卡片风格；用户操作动态更新，不放 Windows 用户数据目录 |
| R09 | 工作目录 config | 动态生成 | 平台用户覆盖、主题生成记录、缓存、锁等；保留，不按临时文件清理 |
| R10 | themes/original、themes/exported | 动态导入/同步/生成，不附带七套完整主题 | 原版和转换结果分开管理；更新前备份，过期结果保留并禁止上传 |
| R11 | library、devices | 动态生成 | 正式本地输出及设备相关资料；使用当次来源和设备状态，默认清理保留 |
| R12 | backups | 动态生成 | 配置迁移前副本、旧主题、扫描/计划/发布及共用素材恢复资料；按批次保留，用户手动选择清理 |
| R13 | temp、logs | 动态生成 | 标记明确的可重建暂存和日志；手动清理，未知资料/当前日志/使用中文件保留 |
| R14 | test_data、references、jobs、artifacts、archive、research/themes/legacy-lab | 不发布；大型本地资料不进 Git | 真实 ROM/主题、设备快照、原包来源、测试报告、实验、旧工程及历史输出；不作为运行时依赖，不随本次文档清理删除 |
| R15 | docs/design/assets/app-icons 四张 PNG 与原 HTML 原型 | 不放运行包；在 Git 保留设计记录 | 当前竖版、横版、翻盖第一款及橙色手柄；ICO 可由工具从竖版原稿重新导出 |
| R16 | tests、tools/themes、tools/migrations、开发虚拟环境 | 不作为正常应用运行资料发布 | 测试、旧逐主题对照、迁移和开发工具；迁移脚本不作为每次启动步骤，不反复执行 |
| R17 | LICENSE 与各依赖/素材要求的声明 | 需要保留适用的许可和来源 | 本项目保留上游 MIT 历史；第三方素材不因进入本项目而自动获得重新许可 |

R01–R17 是本页资源编号，不替代此前讨论的需求编号：第 6 项为通用主题解析，第 7 项为卡片素材，第 11 项为平台升级合并，第 15 项为结果过期，第 17/18 项为清理与恢复资料。原需求清单见 [归档](archive/plans/2026-10-16-windows-approved-scope.md)。

七套完整主题只作为本地真实覆盖样本，原版由用户导入或同步。列表不以“内置七套规则”为由创建空主题，也不要求将开发样本随软件发布。

开发素材目录索引：原版主题 `test_data/themes/original/`、参考主题 `test_data/themes/reference/`、真实 GBA 样本 `test_data/library/real-gba-demo-20261015/`、旧输出 `artifacts/themes/legacy/`、旧主题工程 `archive/FrontendThemeConverter-20261016/`。旧资源位置和清理回执保存在 [历史资源清单](archive/inventories/2026-10-16-resources-before-cleanup.md)。
