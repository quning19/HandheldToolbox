# 本地 Git 工作流

更新日期：2026-10-16。仓库根目录为 FrontendTransTool，当前分支 **main**，产品显示名为“掌机工具箱”。用户要求将功能分支合入主干，合并提交为 `791d7de`，没有冲突。本页只维护当前工作方式；旧分支与建库过程见 [历史记录](archive/workflows/2026-10-16-git-workflow-history.md)。

| 引用 | 用途 |
|---|---|
| main | 已包含今天的独立工具拆分、Windows 功能、修复、测试、图标和文档整理；当前位于此分支 |
| codex/independent-tools | 已通过非快进合并纳入 main，保留原分支和提交用于追溯 |
| codex/<功能名> | 后续确需独立分支时的默认命名；通常从当前 main 创建，延续工作时按实际基点决定 |
| feature/web-app、fix/esde-folder-covers、feature/windows-ui、codex/windows-business | 历史开发阶段，保留用于追溯，不作为当前操作示例 |
| baseline/pre-web-20261014、baseline/windows-ui-20261015、archive/frontend-trans-tool | 保留的历史基线和旧结构快照，不重写或移动 |

在当前分支先读 `git status` 和 `git diff`，仅暂存本次改动，静态 review 后按一个明确目的提交。使用 feat、fix、docs、chore 等清楚描述结果；测试、构建、设备操作仍按明确批准范围执行，不因准备提交而自动扩大检查。

目前只有 upstream（原 retrolibx 来源仓库），没有配置 origin、推送或创建线上 fork。此次仅按用户要求完成本地主干合并，不代表已推送或发布。不能把 upstream 当作本项目发布仓库；后续合并、推送或发布仍依用户要求执行。原上游提交、作者和 MIT 许可保留，具体差异见 [结构与上游关系](ARCHITECTURE.md)。

Git 保存源码、测试源码、配置基线、锁文件、当前文档、历史说明、图标及随包卡片资源。真实 ROM、完整主题、运行设置与工作目录、设备资料、作业报告、旧工程完整归档、虚拟环境和构建产物按 .gitignore 排除。被忽略的真实资料须在本地保留，Git 不提供其备份。

旧 GitHub Actions 放在 docs/archive/retrolibx/github，本项目没有启用根目录 CI 或线上发布。最新改动和测试边界分别见 [调整记录](CHANGELOG.md) 和 [状态](engine/STATUS.md)。
