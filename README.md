# 天马G → 多前端转换

基于RetroLibX扩展，保留通用模型、适配器、操作计划和执行器。当前先实现天马G→Android ES-DE，后续可增加其他目标前端及明确的天马优化步骤。

**当前状态：平台来源、列表合并及来源规则已统一。ES-DE 转换只导出封面、Logo、视频三类素材；共用素材默认关闭，开启时核对复制结果、局部更新原metadata，再清理对应源素材。获批的15个共用素材本地用例已分别取得通过结果，首轮失败项修复后定向复测；未做全量回归或设备执行。设备显示、启动和VIB震动由用户验收。**

- [代码运行入口](retrolibx/README.md)、[当前状态](retrolibx/docs/STATUS.md)：Python 3.12+，功能及验收边界。
- [Windows 图形界面](docs/WINDOWS_GUI.md)：PySide6 / QFluentWidgets 原生 Fluent 工作台预览，根目录双击 `启动界面.cmd`；游戏库和主题业务尚未接入。
- [Android使用说明](retrolibx/docs/ANDROID.md)：scan/capture、多平台build及分步deploy入口；正常执行与专项检查/修复分别授权。
- [ES-DE 素材与天马G共用](retrolibx/docs/SHARED_MEDIA.md)：三类素材、默认关闭的迁移模式及原metadata局部更新。
- [共用平台配置](retrolibx/docs/PLATFORMS.md)：沿用主题转换工具验证过的名称、目录及系统定义。
- [天马来源规则](retrolibx/docs/SOURCE_PROFILES.md)：媒体补找、版本说明及 VIB 确认的配置与选择方式。
- [模型、目录和数据保留说明](retrolibx/docs/PROJECT_GUIDE.md)：合并、排序、完整平台配置、输入输出及 VIB 的实际边界。
- [review处理状态](retrolibx/docs/REVIEW-2026-10-12.md)：已修复及暂缓问题，原报告归档。
- [结果与快照索引](jobs/README.md)、[历史实现记录入口](docs/IMPLEMENTATION.md)。
- [方案](docs/PLAN.md)、[开源评估](docs/OPEN_SOURCE.md)、[资源说明](docs/RESOURCES.md)。

Windows 应用入口为根目录的“启动界面.cmd”，使用说明见 [Windows 图形界面](docs/WINDOWS_GUI.md)。原生页面已开始接入游戏库、平台配置及七套主题业务；这次接入尚未运行测试或设备操作，未打包独立 EXE。

本地Git仓库位于本项目根目录，统一管理retrolibx源码和项目文档。main保存开发基线，feature/windows-ui及baseline/windows-ui-20261015保留界面阶段，codex/windows-business接入实际业务；分支、提交和合并约定见[Git工作流](docs/GIT_WORKFLOW.md)。保留RetroLibX上游历史及MIT许可，上游基于提交f1a73c126ba450ae7d01a856e17ed7aad83eeff9；尚未创建线上fork或推送。upstream保留原项目地址，尚未配置origin。

真实ROM/媒体、设备快照、第三方参考和任务包位于test_data、references与jobs，由Git忽略；源码、当前文档和docs/archive历史文档纳入版本管理。旧superpowers及上游任务表不驱动当前实施，详见[资源清单](docs/RESOURCES.md)。

2026-10-14整理已将部署、计时和metadata启动转换收进源码，过期任务与临时工具收敛为一个恢复归档。最新部署及通过报告保留，见[清理记录](jobs/cleanup-20261014.json)；本轮代码仅静态review，未运行新测试或设备操作。
