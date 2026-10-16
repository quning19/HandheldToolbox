# 项目结构与独立入口

2026-10-16，按用户批准的“独立工具＋汇总 GUI”调整；实现自 `codex/independent-tools`，已通过 `791d7de` 合入本地 `main`，当前位于主干。

```text
FrontendTransTool/
├─ src/
│  ├─ retrolibx/          基于上游修改的通用转换引擎
│  ├─ library_converter/ 游戏库扫描、转换、Android 任务及发布
│  ├─ theme_converter/   主题导入、通用解析、适配、状态及上传
│  ├─ frontend_gui/      页面、控件、Qt 线程及界面卡片资源
│  ├─ frontend_platforms/平台 XML、别名、用户覆盖与升级合并
│  ├─ frontend_devices/  ADB 通信、设备发现与文件捕获
│  └─ frontend_common/   原子配置、取消、任务目录、锁与清理
├─ tests/                engine/conversion/themes/platforms/devices/gui/maintenance
├─ tools/
│  ├─ themes/            迁入的旧构建/打包/校验/角标实验工具
│  └─ migrations/        本次迁移脚本，非应用启动步骤，不应反复执行
├─ docs/                 当前说明；engine/ 业务细节；archive/ 历史材料
├─ examples/retrolibx/    上游示例
├─ research/themes/      调研、旧规则与实验（大型实验文件不进 Git）
├─ test_data/            真实主题与 ROM 样本，本地保存，不发布、不进 Git
├─ artifacts/            历史输出、报告及开发产物，本地保存、不进 Git
├─ archive/              旧项目完整归档，本地保存、不进 Git
├─ workspace/            软件运行数据，不进 Git
├─ settings.json         程序同级的基础设置，不进 Git
├─ pyproject.toml        所有包共用依赖与安装入口
└─ retrolibx/.venv/      本机已有环境，保留位置以免破坏环境内绝对路径
```

两个 converter 是平级业务工具，互不导入，也不导入 GUI 或 Qt。它们复用平台、设备、小型公共模块及通用引擎。GUI 只负责收集参数、调用工具、展示进度和结果。业务模型没有放在 GUI 中。

安装本项目后可以分别运行：

```powershell
python -m library_converter scan 'D:\ROMs' --workspace 'D:\Work'
python -m library_converter convert 'D:\ROMs' --workspace 'D:\Work' --platform GBA
python -m theme_converter import 'D:\Themes\MyTheme' --workspace 'D:\Work'
python -m theme_converter list --workspace 'D:\Work'
python -m theme_converter convert <主题ID> --workspace 'D:\Work'
python -m frontend_gui
python -m retrolibx.cli --help
```

源码目录也提供 `python run_tool.py library|theme|gui|engine ...`，无需安装即可使用同样的模块入口。游戏库设备模式须显式加 `--device`；主题的 refresh/sync/sync-convert/upload 命令明确操作当前唯一设备。普通本地命令不发现或连接设备。

独立运行指各工具不依赖 GUI 和另一个业务工具；当前仍共用一个安装包与环境，不为每个工具复制一套共享源码或依赖。以后加入 PegasusGGameManager 一类工具时，在 `src/` 新增平级包和独立入口，再在 `frontend_gui/` 接入页面；本次没有搬入该项目，也没有预设空业务框架。

## 旧主题工程迁移

旧工程完整保留在 `archive/FrontendThemeConverter-20261016/`，不再作为 Python 的运行时依赖。七套原版到 `test_data/themes/original/`；参考主题到 `test_data/themes/reference/`；旧 dist 到 `artifacts/themes/legacy/`；lab 到 `research/themes/legacy-lab/`；旧脚本与配置到 `tools/themes/`；测试到 `tests/themes/test_legacy_batches.py`。原文档及映射见 [迁移记录](archive/frontend-theme-converter/MIGRATION.json)。

旧的 build/package/validate/verify/badge 脚本可从根目录直接 `python tools/themes/<脚本>.py ...`，路径由新的 common.py 解析。它们保留逐主题规则供回归对照，不是 GUI 的主题转换后端。旧 shell 权限修复脚本仅作为历史资料归档，不进入正常转换。

真实 GBA 样本迁到 `test_data/library/real-gba-demo-20261015/`，没有删除或重新上传设备。旧 scan/convert 作业从 temp 迁至 backups/library，绝对本地 JSON 引用同步迁移并保留迁移前副本；其他不明 temp 文件保留。

## retrolibx 与上游的关系

这是保留上游 Git 历史和 MIT 许可的修改版本，来源为 [tiancheng91/retrolibx](https://github.com/tiancheng91/retrolibx)，基点 `f1a73c126ba450ae7d01a856e17ed7aad83eeff9`。不是原封不动的 vendor 副本，也不能用 PyPI 的同名原版直接替换。原作者信息与 LICENSE 保留；没有创建线上 fork 或推送。

迁移前静态对照：上游 35 个源码文件全部保留，其中 23 个未改、12 个改动；当时额外增加 58 个源码/资源文件。本次将设备、业务和 GUI 扩展移出引擎目录，文件位置变化不代表回退这些修改。

| 引擎内改动区域 | 与上游的差异 |
|---|---|
| Pegasus adapter / metadata | 天马 G 多版本、嵌套路径、原始字段及媒体规则 |
| ES-DE adapter | 三类素材、文件夹封面、平台路径及游戏列表输出 |
| application/service | 统一平台、来源 profile、诊断和转换编排 |
| core planner/executor/operations/options | 受限写入、基线保护、备份及可选共用素材迁移 |
| core validation / utils discovery | 现存 ROM、描述文件从属关系、路径及编码约束 |
| registry/systems | 读取统一平台目录与完整四文件基线 |
| cli | 保留原命令，调用拆出的 Android 工具模块 |

引擎继续遵守 Adapter → Library → ExportIntent → Planner → Executor。主题文件复制也使用 Planner/Executor；最终受管理目录替换单独保留可恢复旧版本。
