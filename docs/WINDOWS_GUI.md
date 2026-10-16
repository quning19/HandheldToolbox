# Windows 图形界面

2026-10-16。显示布局沿用已确认的 Fluent 工作台，窗口尺寸和固定进度区不变。源码已拆为独立工具和汇总 GUI，见 [结构](ARCHITECTURE.md)。

本机双击根目录“启动界面.cmd”，或：

```powershell
& '.\retrolibx\.venv\Scripts\python.exe' '.\launch_gui.py'
```

其他机器安装 `pip install -e '.[desktop]'` 后运行 `python -m frontend_gui`。当前开发环境不等于独立 EXE 发布。目录迁移后应关闭旧进程，再重新打开。

游戏库页面保持手动刷新设备、选择来源后手动加载、后台逐平台追加卡片。ROM 计数、多版本、多轨、封面、增量跳过与全量替换、共用素材及完整四文件初始化规则保持。电脑目标自动放在 workspace/library；设备目标自动识别 ES-DE。MuMu 连接在用户点击刷新后发现运行实例端口，不启动模拟器。

主题页面初次可以为空；导入本地主题，或刷新设备后选择真实主题同步。操作为导入本地、同步原版、同步并转换、转换、上传。状态分别显示本地原版、可上传/需要重新转换/失败、设备是否存在；错误及过期原因在提示中。未知结构保留错误报告，不冒充转换成功。见 [主题规则](THEME_CONVERSION.md)。

设置包含亮暗外观、平台卡片风格（Canvas/Aura/Alekfull NX/iiSU Interpreted）、唯一工作目录、平台增删改及 [三类手动清理](WORKSPACE_DATA.md)。风格切换只换平台卡片，缺少专用图时使用同风格母体图或占位。

测试批准范围和结果集中记录在 [状态](engine/STATUS.md)。本轮不自动操作窗口、连接模拟器或写入设备，页面由用户手动验收。迁移前业务和既有测试记录保存在 [2026-10-15 记录](archive/windows-gui-business-20261015.md)。
