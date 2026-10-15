# RetroLibX · 天马G转换扩展

将天马G/Pegasus游戏库转换为Android ES-DE列表和媒体，保留RetroLibX的通用模型及其他前端适配器。

平台配置共用、已有列表合并、来源规则和Android任务生成已实现。ES-DE 转换只导出封面、Logo、视频三类素材。共用素材默认关闭；明确开启后核对所有目标副本、局部更新原metadata，再清理对应源素材，见 [SHARED_MEDIA.md](docs/SHARED_MEDIA.md)。获批的15个共用素材本地用例已分别取得通过结果，失败项修复后定向复测；这部分未做全量回归或共用迁移设备执行。新增的 `upload` 默认预览，`--apply` 才按 C2/C4 上传；新增上传用例未执行。完整状态见[STATUS.md](docs/STATUS.md)。

## 使用当前源码

Windows 原生应用可从外层项目根目录双击“启动界面.cmd”打开。已接入实际游戏库和主题服务，使用及测试边界见 [Windows 图形界面](../docs/WINDOWS_GUI.md)；获批的 29 项本地测试通过，界面与真实设备联调待用户操作，尚未打包。

需要Python 3.12+，依赖由[pyproject.toml](pyproject.toml)声明、[uv.lock](uv.lock)固定。在本仓库目录使用现有`.venv`运行：

```powershell
& '.\.venv\Scripts\python.exe' -m retrolibx.cli scan --config examples/profile.local.json
& '.\.venv\Scripts\python.exe' -m retrolibx.cli build --config examples/profile.local.json --platform GBA --out jobs/gba
```

配置例子指向外层真实节选及MuMu独立目录，使用前按实际环境调整。`build`可重复指定`--platform`，一次生成多个平台的一份任务，不需要逐平台生成后拼接。生成不应用到设备。`deploy`默认本地预览，`--apply`才执行上传、设备内复制和电脑端XML发布；`--stage upload|copy|publish`限定单步，`--skip-platform-config`排除平台配置。结果和阶段耗时保存在任务目录。原有`upload`、`publish`入口保留。普通convert默认复制ROM；Android流程将ROM留在原目录，共用关闭。额外资源检查与修复独立授权。详细使用见[ANDROID.md](docs/ANDROID.md)。本轮整理及新增用例仅静态review，未运行测试或设备操作。

## 文档入口

| 文档 | 内容 |
|---|---|
| [STATUS.md](docs/STATUS.md) | 实现状态、检查范围及待验收事项 |
| [ANDROID.md](docs/ANDROID.md) | scan、capture、build、C2/C4 upload及任务包使用 |
| [PROJECT_GUIDE.md](docs/PROJECT_GUIDE.md) | 模型、目录、合并和排序边界 |
| [PLATFORMS.md](docs/PLATFORMS.md) | 完整平台XML基线及识别 |
| [SOURCE_PROFILES.md](docs/SOURCE_PROFILES.md) | 普通Pegasus与天马G来源规则 |
| [review处理状态](docs/REVIEW-2026-10-12.md) | 已修复问题及暂缓事项 |
| [历史资料](docs/archive/README.md) | 上游设计、旧模板及原review |

## 仓库结构

```text
src/frontend_platforms/   共用平台加载、补充信息与发布用XML副本
src/retrolibx/            模型、适配器、计划、执行器、CLI
src/retrolibx/profiles/   来源规则JSON
tests/                   测试源码，按用户批准范围执行
examples/                本地配置例子
docs/                    当前说明；archive/保存历史资料
```

真实ROM、设备快照和任务在外层工作区。运行环境、缓存及输出均忽略。平台维护基线来自相邻FrontendThemeConverter，独立安装使用声明的发布副本。

基于上游提交`f1a73c126ba450ae7d01a856e17ed7aad83eeff9`，保留Git历史与[MIT许可](LICENSE)。第三方ES-DE模板许可随[历史模板](docs/archive/templates/NOTICE.md)保留。Git仓库已提升到FrontendTransTool根目录，当前实现已提交到本地`main`基线，后续Web开发使用`feature/web-app`；尚未推送。详见[Git工作流](../docs/GIT_WORKFLOW.md)。
