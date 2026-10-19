# 掌机工具箱 · HandheldToolbox

面向 Windows 的天马 G / Pegasus → Android ES-DE 工具箱，提供游戏库转换、官方主题下载与适配，以及设备上传。

## 功能

- **游戏库转换**：识别平台与游戏资料，生成 ES-DE 游戏列表和平台配置；支持增量／全量、封面与视频处理、Android 设备发布。
- **主题管理**：浏览 ES-DE 官方主题目录与预览图，搜索筛选，批量下载／更新、检查更新、适配转换和上传；分别显示原版、适配和设备状态。
- **本地管理**：导入本地主题，保留原版与转换结果，提供工作目录、备份、平台配置和外观设置。

主题适配用于让 **ES-DE 识别天马 G 的游戏平台目录**，转换结果仍由 ES-DE 使用。游戏库和主题工具均提供独立命令行入口。

## 安装与启动

需要 Windows、Python 3.12+；官方主题下载需要 Git。设备上传还需要 Android Platform Tools（ADB），并在设备上开启 USB 调试、授权电脑。

在 PowerShell 中执行：

```powershell
git clone https://github.com/quning19/HandheldToolbox.git
cd HandheldToolbox
py -3.12 -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -e '.[desktop]'
& '.\.venv\Scripts\python.exe' -m frontend_gui
```

Git 应加入 PATH；ADB 可加入 PATH，也可通过标准 Android SDK 目录或 `ANDROID_HOME` / `ANDROID_SDK_ROOT` 定位。使用更新版本的 Python 时，相应替换上述 `py -3.12`。

当前提供源码运行方式，尚未发布独立 EXE。根目录 `.cmd` 启动器使用维护环境 `retrolibx/.venv`；按上述步骤安装后，使用给出的 Python 命令启动。

## 基本使用

1. 在设置中确认工作目录；原版主题、转换结果、日志和备份均由此管理。
2. **游戏库转换**：选择天马 G 来源，加载平台并配置转换范围；需要发布时连接设备，再执行转换与上传。
3. **主题管理**：刷新官方目录，点击主题查看预览；勾选主题后下载／更新，再转换、上传。点击列表行只切换预览，批量操作以复选框为准。

原版更新后，已有适配结果可能需要重新转换。上传前确认设备和目标目录；可选共用素材功能会更新来源 metadata 及清理对应素材，使用前请阅读[共用素材说明](docs/engine/SHARED_MEDIA.md)。

## 命令行

安装后，在同一 Python 环境中查看各工具帮助：

```powershell
& '.\.venv\Scripts\python.exe' -m library_converter --help
& '.\.venv\Scripts\python.exe' -m theme_converter --help
& '.\.venv\Scripts\python.exe' -m retrolibx.cli --help
```

图形界面入口为 `python -m frontend_gui`。也可从源码根目录使用 `python run_tool.py library|theme|gui|engine ...`。

## 文档

| 文档 | 内容 |
|---|---|
| [Windows 界面](docs/WINDOWS_GUI.md) | 页面和操作说明 |
| [主题适配](docs/THEME_CONVERSION.md) | 下载更新、转换规则与支持边界 |
| [Android 发布](docs/engine/ANDROID.md) | 设备任务与发布流程 |
| [工作目录](docs/WORKSPACE_DATA.md) | 数据、备份与清理规则 |
| [项目结构](docs/ARCHITECTURE.md) | 独立工具和上游关系 |
| [当前状态](docs/engine/STATUS.md) / [调整记录](docs/CHANGELOG.md) | 实现、测试记录及后续安排 |

真实 ROM、完整下载主题、个人设置、工作目录和虚拟环境不进入仓库。自动化测试与手动验收的范围见当前状态；源码发布不代表已完成独立 EXE 的打包验收。

## 许可与致谢

HandheldToolbox 应用按 **GPL-3.0-only** 发布，全文见 [LICENSE](LICENSE)。

- 基于 [tiancheng91/retrolibx](https://github.com/tiancheng91/retrolibx) 扩展，保留上游 Git 历史及[原 MIT 声明](docs/licenses/RetroLibX-MIT.txt)；`upstream` 继续指向该项目。
- 官方主题管理参考 [ES-DE](https://gitlab.com/es-de/emulationstation-de) 的主题下载器与官方主题目录，保留[相关 MIT 声明](docs/licenses/ES-DE.txt)。
- Windows 界面使用 PySide6 和 [QFluentWidgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets/tree/PySide6)。

第三方主题、预览图、平台卡片和标识分别适用其原许可，不由本项目统一改授 GPL。部分卡片来源声明包含非商业与相同方式共享条件；具体来源、许可差异及待确认项见 [NOTICE](NOTICE.md)。
