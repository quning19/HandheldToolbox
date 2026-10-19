# Windows 图形界面

本机双击根目录“掌机工具箱.cmd”（旧“启动界面.cmd”保留），或在根目录运行：

```powershell
& '.\retrolibx\.venv\Scripts\python.exe' '.\launch_gui.py'
```

其他机器使用 Python 3.12+ 安装 `pip install -e '.[desktop]'` 后运行 `HandheldToolbox` 或 `python -m frontend_gui`。安装入口依赖 Python，独立 EXE 尚未打包。

| 页面 | 用途 |
|---|---|
| 游戏库转换 | 手动连接设备、加载所选来源的平台，执行天马G → ES-DE 转换与发布 |
| 主题管理 | 浏览官方主题与图集，勾选后下载／更新、转换或上传；点击行只切换预览 |
| 设置 | 外观、四套卡片风格、唯一工作目录、平台管理及工作目录清理 |

软件使用“掌机工具箱”名称及选定竖版图标，原稿见 [图标资源](design/assets/app-icons/README.md)。

详细交互统一见 [页面约定](WINDOWS_UI_PLAN.md)，主题规则见 [主题说明](THEME_CONVERSION.md)，数据保留规则见 [工作目录与清理](WORKSPACE_DATA.md)。用户手测反馈和测试边界统一记录在 [当前状态](engine/STATUS.md)。
