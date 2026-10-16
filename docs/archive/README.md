# 历史资料

保存旧方案、研究和实施证据。历史内容中的“当前”“已确认”“待办”和执行要求只代表原阶段，不驱动现在的操作。当前以用户要求、适用 AGENTS.md、[状态](../engine/STATUS.md)及[后续计划](../PLAN.md)为准。

## 2026-10-16 文档整理

| 归档 | 原位置及过期原因 |
|---|---|
| [2026-10-14 计划](plans/2026-10-14-plan.md) | 原 PLAN.md，仍以界面未接业务为下一步 |
| [旧实施索引](implementation/2026-10-16-implementation-index.md) | 原 IMPLEMENTATION.md，历史测试入口重复；当前改用 CHANGELOG 与 STATUS |
| [旧资源清单](inventories/2026-10-16-resources-before-cleanup.md) | 原 RESOURCES.md，包含旧目录及过去清理回执 |
| [Git 分支与建库过程](workflows/2026-10-16-git-workflow-history.md) | 原 GIT_WORKFLOW.md，Web 分支操作不再适用当前工作 |
| [Windows 原批准清单](plans/2026-10-16-windows-approved-scope.md) | 原 WINDOWS_UI_PLAN.md，已实现项目仍为未勾选待办；原文保留作需求依据 |
| [开源选型与原版实测](evaluations/2026-10-12-open-source-assessment.md) | 原 OPEN_SOURCE.md，原版评估不能代表当前改造版 |
| [拆分前工程说明](../engine/archive/guides/2026-10-16-project-guide-before-split.md) | 原 engine/PROJECT_GUIDE.md，旧相邻工程及目录不再参与运行 |

当前职责分开：CHANGELOG 记录发生的调整，STATUS 记录实现/测试/验收事实，PLAN 只列剩余工作。上述归档已调整相对链接并标注原位置；其他更早资料保留原阶段语境，设备路径、测试产物链接仅用于追溯，不作为当前参数。

## 更早记录

- [旧技术方案](superpowers/specs/2026-10-10-pegasus-to-esde-python-design.md)
- [旧实施任务表](superpowers/plans/2026-10-12-frontend-trans-tool.md)
- [旧执行账本](superpowers/progress.md)：停在Task 1，没有产品实现。
- [旧接口测试](superpowers/test_reading.py)：不参与新方案的unittest发现。
- [第三方初评](evaluations/2026-10-12-third-party-tools-assessment.md)
- [封面工具实测](evaluations/2026-10-12-cover-converter-fixture-results.md)
- [游典派生样本实测](evaluations/2026-10-12-youdian-fixture-results.md)
- [设备成功对照与结论修正](evaluations/2026-10-12-device-gba-ruby-review.md)
- [整理前完整方案](plans/2026-10-12-before-cleanup.md)
- [开发与检查过程](implementation/2026-10-12-before-cleanup.md)：按时间理解，当前状态看[STATUS](../engine/STATUS.md)。

初评的源码复用建议已退出当前范围。失败样本需结合成功对照阅读，不推广到所有输入。
