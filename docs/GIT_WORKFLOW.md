# 本地 Git 工作流

2026-10-14建立。仓库根目录为`FrontendTransTool/`，Python源码和运行入口仍在`retrolibx/`；本次没有实现Web应用或改动业务逻辑。

## 分支与基线

| 引用 | 用途 |
|---|---|
| `main` | 当前已提交的开发基线；功能完成并review后合入。基线提交不代表测试通过或可发布 |
| `feature/web-app` | 从当前main创建的Web开发分支，本次结束时所在分支 |
| `codex/<功能名>` | 新任务默认分支前缀；已有 feature/fix 分支保留，保持提交范围清楚 |
| `archive/frontend-trans-tool` | 仓库提升前的代码快照，仅供追溯；该分支采用旧的源码根目录布局 |
| `baseline/pre-web-20261014` | 仓库提升后的带注释标签，记录Web改造前基线 |

已有上游5条提交及`v0.1.0`标签原样保留。本次新增两条提交：先保存现有Pegasus G/Android ES-DE实现，再记录根目录提升、外层文档纳入和Git工作流。没有重写上游历史，也没有将累计改动伪拆成过去的开发记录。

`archive/frontend-trans-tool`及上游提交中的路径没有`retrolibx/`前缀。日常开发使用main及其功能分支；查看旧历史可用`git show`，切换旧分支会恢复旧目录布局。

## 日常操作

命令在项目根目录执行。Web工作已经有分支，直接使用：

```powershell
git switch feature/web-app
git status
git diff
git add <本次相关文件>
git diff --cached
git commit -m "feat: describe the concrete change"
```

其他任务从main创建分支，例如：

```powershell
git switch main
git switch -c fix/<问题名>
```

提交按一个明确目的组织，使用`feat:`、`fix:`、`docs:`或`chore:`开头，说明具体结果。合入前review源码和diff；测试、lint、类型检查、构建仍须用户明确批准，不能以提交或合并为由自动执行。完成review及用户已批准的检查后，在干净工作区合入：

```powershell
git switch main
git merge --no-ff feature/web-app -m "merge: integrate web application"
```

该合并命令是后续流程说明，本次未合并Web功能。基线标签保留，不随开发移动；需要追溯时使用`git log --graph --oneline --decorate --all`或`git show baseline/pre-web-20261014`。

## 跟踪范围与远程

2026-10-14后续需求已转为Windows应用，页面方案见[界面记录](WINDOWS_UI_PLAN.md)。feature/web-app保留原始名称与基线；fix/esde-folder-covers保存方案记录和子目录封面修复，10个获批局部用例通过，设备补齐 GBA hack 8 个与 PS1 4 个文件夹封面。feature/windows-ui从该修复分支继续，保存原生界面与模拟交互阶段；实际业务继续在codex/windows-business开发，未合入main或推送。

- 纳入：项目README、docs及历史文档、retrolibx源码、测试源码、配置、锁文件及许可。
- 忽略：test_data、references、jobs、.deps、虚拟环境、缓存、构建产物、node_modules及本地.env文件。被忽略的本地数据不由Git保存。
- `upstream`保留`https://github.com/tiancheng91/retrolibx.git`，供来源追溯；main不跟踪upstream/main，避免日常pull误用原项目分支。
- 尚未配置origin、创建线上仓库或推送；现有Git作者信息继续使用本机配置。
- 原GitHub Actions文件仍在`retrolibx/.github/workflows/`，作为原项目配置保留。当前没有启用根目录CI或线上发布；后续接入远程时再按项目结构处理。

仓库初始化时仅静态查看Git状态、文件清单及文档diff，未执行测试、lint、类型检查、构建或设备操作。后续文件夹封面修复的获批测试范围见上述记录。

2026-10-15 用户确认暂时保留当前显示效果。`feature/windows-ui` 保存原生界面、亮暗主题及侧栏/固定进度区修复；该节点标记为 `baseline/windows-ui-20261015`，作为接入业务前的可回退版本。此基线仅表示界面阶段归档，不表示最新改动已经通过测试。实际业务在从此节点创建的 `codex/windows-business` 分支继续，后续新分支默认使用 `codex/` 前缀。没有合入 main 或推送远程。

实际业务通过 44cf2e9（应用服务、主题规则、局部用例）及 2c4a2df（界面调用）分开记录。Python 依赖及锁文件已包含 Pillow，主题运行不依赖相邻工程路径。用户批准的 29 项本地测试已对 2c4a2df 执行一次并全部通过（5.09 秒），未改动业务源码，无修复复测；本轮没有窗口或设备操作。详细范围见 [Windows 图形界面](WINDOWS_GUI.md)。
