# Windows 图形界面开发

2026-10-14。当前分支 `feature/windows-ui`，首版为 **PySide6 / Qt Widgets / QFluentWidgets 原生界面预览**。页面布局沿用 [确认方案](WINDOWS_UI_PLAN.md)，不调用转换核心、主题工具或 ADB。

## 打开界面

本机已在 `retrolibx/.venv` 安装桌面依赖。双击项目根目录的 `启动界面.cmd`，或者在根目录执行：

```powershell
& '.\retrolibx\.venv\Scripts\python.exe' -B '.\launch_gui.py'
```

其他机器需要 Python 3.12+，先建立虚拟环境并安装依赖：

```powershell
python -m venv retrolibx/.venv
& '.\retrolibx\.venv\Scripts\python.exe' -m pip install -r retrolibx/requirements-desktop.txt
```

已安装完整 Python 项目时，可安装桌面可选依赖 `pip install -e "retrolibx[desktop]"`，通过 `frontend-trans-tool` 启动。CLI 原有依赖不强制引入 Qt。

当前尚未打包独立 EXE。运行、界面自动化、截图、测试和打包验证均需单独取得用户批准；上述命令是用户运行入口，不代表已由开发者验证通过。

## 首版范围

| 页面 | 已实现的界面及交互 | 当前数据/操作 |
|---|---|---|
| 游戏库转换 | 掌机/电脑来源切换、候选目录、手动加载、逐平台异步追加、取消、网格多选、共用素材、全量替换、进度/结果 | 示例平台和数量，转换只更新内存中的示例收录状态 |
| 主题适配 | 七套主题、本地原版/转换结果/设备状态、同步/转换/上传/刷新、批量选择、取消 | 示例状态和进度，不执行下载、转换或上传 |
| 设置 | 唯一工作目录、自动创建功能子目录、程序同级基础设置 | 点击保存后实际写入本地配置 |
| 平台管理 | 搜索、添加、编辑、删除、母体引用保护、重复目录校验 | 实际写入工作目录的平台配置；暂未用于真实转换 |

窗口默认 1140 × 750，最小 1000 × 650，使用 Windows 原生标题栏和边缘缩放。页面切换只切换内容，不重新设定窗口尺寸；平台网格按当前宽度重排，固定 10px 行列间距，列表区域内部滚动。加载时修改来源会中止旧任务，旧信号通过代次标识丢弃；窗口关闭时等待短任务退出，防止线程被提前销毁。

平台卡片使用已确认 HTML 原型里的 14 张 Canvas capsule WebP 显示副本，不依赖设备或外部主题路径。上部图片铺满、名称居中描边，下部显示 ROM、封面和新增数量。PSP Minis 暂沿用 PSP 卡图。

## 保存位置

源码模式的 `settings.json` 位于项目根目录，与 `launch_gui.py` 同级；冻结为 EXE 时位于 EXE 同级。不使用 AppData。首次打开只读取配置，不自动写入。

默认工作目录为程序同级的 `workspace/`，也可在设置页选择其他绝对路径。保存工作目录后自动创建 `config/`、`themes/original/`、`themes/exported/`、`library/`、`devices/`、`logs/`、`temp/`。切换目录使用新位置的平台定义，不搬移旧数据。

平台定义保存在 `<workspace>/config/platforms.json`，包含版本、显示名称、目录、内部标识、母体、主题表现和角标。这是界面层配置，**尚未替代** Python 核心的 `frontend_platforms` 平台定义；接入时需统一映射，并保留已有 GBA vib 启动规则。示例转换、主题结果与示例设备状态不保存为真实产物或部署记录。

## 源码拆分

```text
retrolibx/src/retrolibx/gui/
├─ app.py              主窗口、导航、状态栏、启动入口
├─ library_page.py     来源、后台示例加载、游戏库交互
├─ themes_page.py      主题状态和示例操作
├─ settings_page.py    工作目录及平台管理
├─ widgets.py          平台卡片、网格、页内反馈控件
├─ state.py            示例数据、界面平台模型、便携配置
└─ assets/platforms/   既有原型的 Canvas 缩略图
```

业务接入应继续使用原有 Adapter → Library → ExportIntent → Planner → Executor 流程；页面不自行拷贝媒体、修改 gamelist 或通过临时脚本部署。当前没有新增扫描业务、数据库、更新器、任务历史页面或设备写入。

## 依赖与检查边界

安装版本为 PySide6 6.12.0、PySide6-Fluent-Widgets 1.11.3。版本在可选依赖、桌面依赖清单和项目锁文件维护。[Qt for Python](https://doc.qt.io/qtforpython-6/) 与 [QFluentWidgets 安装说明](https://qfluentwidgets.com/pages/install/) 为 API 依据。

核心原有 MIT 许可保持；QFluentWidgets 开源版使用 GPLv3，桌面发行须遵循其许可，不能将整个桌面发行物直接视为 MIT。[QFluentWidgets 包与许可](https://pypi.org/project/PySide6-Fluent-Widgets/)。Canvas 缩略图沿用既有设计演示资源，独立软件发行前需确认主题原素材的分发授权。

本轮完成源码、调用关系、线程取消、目录保存与边界的静态 review。未执行单元测试、lint、类型检查、构建或设备操作；尚未启动界面，实际显示与交互等待获批的本地检查。
