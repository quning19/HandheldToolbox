# 掌机工具箱

Windows Fluent 工作台，汇总独立的游戏库转换和 ES-DE 主题适配工具。工程目录保留 FrontendTransTool，Python 模块入口沿用原名。

- `library_converter`：天马 G → ES-DE，自动平台配置、增量/全量、可选共用素材、文件夹封面及 Android 发布。
- `theme_converter`：本地导入/设备同步原版，通用 ES-DE 资源解析、适配、保留结果及上传。
- `frontend_gui`：页面、参数和结果展示；两个业务工具均可脱离 GUI 独立执行。
- `retrolibx`：保留上游历史、MIT 许可及多前端能力的修改版引擎。

本机双击“掌机工具箱.cmd”（原“启动界面.cmd”仍可使用）。Python 3.12+ 环境也可在项目根目录安装：

```powershell
python -m pip install -e '.[desktop]'
python -m frontend_gui
python -m library_converter --help
python -m theme_converter --help
python -m retrolibx.cli --help
```

源码入口：`python run_tool.py library|theme|gui|engine ...`。原有本机环境保留在 retrolibx/.venv，不复制或重建。

应用图标选用竖版掌机 1，窗口和侧栏统一使用；四张保留原稿及说明见 [图标资源](docs/design/assets/app-icons/README.md)。同名 Python GUI 入口安装后在 Windows 生成“掌机工具箱.exe”；独立 EXE 尚未打包。

| 说明 | 内容 |
|---|---|
| [调整记录](docs/CHANGELOG.md) | 今天的实施范围、提交、测试及文档整理 |
| [后续计划](docs/PLAN.md) | 名称/图标、实际窗口、设备联调及独立发布的剩余工作 |
| [结构与独立入口](docs/ARCHITECTURE.md) | 包职责、依赖方向、旧主题工程迁移、与 retrolibx 上游的关系 |
| [Windows 界面](docs/WINDOWS_GUI.md) | 实际页面和手动验收入口 |
| [通用主题解析](docs/THEME_CONVERSION.md) | XML/变量/分支、素材策略、过期判断及支持边界 |
| [工作目录与清理](docs/WORKSPACE_DATA.md) | 静态资源、动态数据、备份、手动清理规则 |
| [发布数据清单](docs/RESOURCES.md) | 随包资源、动态资料和开发样本的编号清单 |
| [统一平台](docs/engine/PLATFORMS.md) | 完整四文件基线、用户覆盖及升级合并 |
| [Android 细节](docs/engine/ANDROID.md) | 原 scan/capture/build/deploy 命令 |
| [共用素材](docs/engine/SHARED_MEDIA.md) | 开启后的副本核对、metadata 局部更新及源媒体清理 |
| [当前状态](docs/engine/STATUS.md) | 当前实现与测试/设备/发布的实际边界 |
| [Git 工作流](docs/GIT_WORKFLOW.md) | 分支、历史与提交规则 |
| [历史资料](docs/archive/README.md) | 已归档的旧计划、研究与实施证据 |

基础设置保存在程序同级 settings.json；全部运行资料由唯一 workspace 管理。真实 ROM、完整第三方主题、历史产物和旧项目归档保留在本地，均不进入 Git 或应用包。平台卡片资源保留来源/许可记录，独立软件分发仍需按各主题素材许可处理；当前没有打包或发布 EXE。

本轮在 `codex/independent-tools` 实施，已通过 `791d7de` 合入本地 `main`，当前位于主干。[先前 72 项本地测试](docs/TESTS_INDEPENDENT_TOOLS_20261016.md)已分别取得通过结果。[后续功能测试](docs/TESTS_FUNCTIONAL_20261016.md)覆盖七套真实主题完整导出、三项离屏 GUI 检查及真实 GBA 增量流程；48 项首轮有一项失败，修复 ROM 路径误匹配后，17 项定向测试全部通过，没有重跑整批测试。名称与图标此后接入，仅做静态 review；实际窗口外观、设备与发布仍分别验收，剩余事项见 [计划](docs/PLAN.md)。
