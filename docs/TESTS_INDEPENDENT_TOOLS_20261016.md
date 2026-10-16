# 独立工具改造：获批本地测试记录

分支 `codex/independent-tools`，初始实现提交 `a6fc2e4`。用户先明确批准 72 项及一次失败项定向复测，随后另行批准 Iconic 一项复测一次。没有扩大测试范围，也没有将通过项重复运行。

本页保留该批次的执行事实；后续七套主题完整导出、离屏 GUI 与真实 GBA 流程见 [后续功能测试](TESTS_FUNCTIONAL_20261016.md)，最终当前边界见 [状态](engine/STATUS.md)。下面的“尚未导出”描述仅对应本批次结束时。

| 执行阶段 | 范围 | 结果 | 耗时 |
|---|---|---|---|
| 首轮 | 新增 34 项＋既有 38 项，共 72 项 | 66 项通过；6 套真实主题的方法失败；无跳过 | 19.078 秒 |
| 获批定向复测 | 首轮失败的 6 项 | Alekfull NX、Aura、Canvas、Elementerial、PlayStation-X 通过；Iconic 仍失败 | 32.422 秒 |
| 另行获批复测 | 仅 Iconic，一项含 12 个平台分支 | 通过；无错误、无跳过 | 2.922 秒 |

72 个不同用例累计均已取得通过结果；共执行 79 次方法调用。没有在最后修复后重跑全部 72 项，不应将结果表述为最终代码的一次全量通过。七套真实主题各覆盖默认定义中的 12 个独立衍生平台，共 84 个主题/平台组合。

## 覆盖范围

| 模块 | 用例数 |
|---|---:|
| 通用解析语义 | 9 |
| 七套真实主题资源图 | 7 |
| 动态主题列表、依赖及内容摘要 | 4 |
| 默认平台与用户覆盖合并 | 6 |
| 清理选择、变化保护和工作锁 | 5 |
| 独立 CLI 与无 Qt 业务导入 | 3 |
| 既有便携配置 | 9 |
| 既有游戏库及主题业务 | 19 |
| 既有模拟器识别（模拟进程/ADB） | 10 |

## 修复

- 主题 XML 改为按实际引用加载。原先遍历解析整个主题目录，把未引用的模板和草稿当作运行输入，导致 Aura、Canvas、Elementerial、Iconic 初始化失败。
- 配置 XML 继续严格解析；主题读取保留 ES-DE 选择第一个 theme 文档元素的语义，错误信息附上来源文件。
- 区分插画、硬件图、普通平台图标及装饰层。包含 icons 的目录不使 capsule/art/controller 插画失去用途；普通图标仍原样继承。
- 轮播/网格的可选自定义图允许使用原主题文字回退；有对应基础图层的 custom 层可以留空；原版未提供的装饰覆盖层保持为空并报告，不将其误判成必须补齐的主体素材。
- 解析器与素材策略版本分别更新，旧结果会要求重新转换。没有为七个主题添加按名称分派的专用配置。

文字回退依据 [ES-DE 主题文档](https://gitlab.com/es-de/emulationstation-de/-/blob/master/THEMES.md) 中 carousel/grid 的 staticImage、defaultImage、text 行为；自定义图层结合实际 XML 的基础图层引用和已有主题说明处理。

## 证据与边界

执行器为 [限定测试入口](../tools/run_approved_independent_checks.py)，每个阶段写入报告后禁止重复执行，避免超出批准次数。

- [首轮报告](../jobs/independent-tools-check-20261016/initial.json)、[日志](../jobs/independent-tools-check-20261016/initial.log)
- [第一次定向复测](../jobs/independent-tools-check-20261016/failed.json)、[日志](../jobs/independent-tools-check-20261016/failed.log)
- [Iconic 复测](../jobs/independent-tools-check-20261016/iconic.json)、[日志](../jobs/independent-tools-check-20261016/iconic.log)

jobs 报告仅本地保存；本页保存纳入 Git 的摘要。测试只使用临时配置、测试副本或模拟 ADB；七套真实主题只读解析，没有改写原版。未操作窗口、连接设备、打包、执行 lint/类型检查、清理真实工作目录，也未执行旧主题工具的额外校验。

真实主题验收覆盖资源引用、分支和平台推导，不等于七套完整主题导出和 ES-DE 实际显示已验收。完整生成/上传及视觉、启动等仍需后续单独授权和用户确认。
