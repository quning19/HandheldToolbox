# 资源与目录清单

2026-10-16 结构已调整：产品代码在根目录 src，当前资源分类见 [ARCHITECTURE](ARCHITECTURE.md) 和 [工作目录](WORKSPACE_DATA.md)。七套完整真实主题、旧 dist/lab、原项目完整归档及 GBA 样本均在本地保留，运行时不依赖旧相邻项目。以下为 2026-10-14 历史资源清单与清理记录，旧路径用于追溯；分支约定见 [Git 工作流](GIT_WORKFLOW.md)。

| 位置 | 用途及保留规则 |
|---|---|
| retrolibx/src、tests、examples、docs | 产品代码、测试源码、本地配置与当前说明 |
| retrolibx/.venv | 当前运行环境，保留、不提交 |
| test_data/original_excerpt/Roms | 当前真实输入：3个平台、15个ROM，保持原字节 |
| original_excerpt/manifest.json、expected.json | 来源清单及逐ROM预期，保留 |
| original_excerpt/output | 旧导出证据，不当作当前配置基线 |
| test_data/research、test_data/archive | 评估/样本结果、历史24-ROM派生包及设备成功对照 |
| jobs | 导出、任务、索引、设备快照及报告，见[索引](../jobs/README.md) |
| references/tools、references/apks | 原第三方工具、说明和APK，保留，不作为运行依赖 |
| docs/archive | 旧方案、评估和详细过程，不驱动实施 |
| docs/engine/archive | 上游设计、原review、旧模板及许可 |
| .deps/tooling | 本地uv工具保留，uv-cache可清理 |
| .deps/theme-tests-py39 | 已准备的主题项目Python 3.9依赖，保留 |

## 本轮清理

2026-10-14将过期候选任务、临时部署/检查脚本、测试temp和字节码缓存移出工作目录；通过报告、最新部署产出、原始快照、真实样本及环境保留。自动审批拒绝直接永久删除后，改为先保存并核对恢复归档，再移除工作目录副本。清单见[jobs/cleanup-20261014.json](../jobs/cleanup-20261014.json)，归档见[jobs/archive/cleanup-20261014.zip](../jobs/archive/cleanup-20261014.zip)。历史配置仍引用的PSP Minis模板保留，未来任务用代码中的system_templates配置。不运行测试、lint、构建或设备操作。

以下是2026-10-12的旧清理记录：

删除候选源码及研究依赖副本.deps/research、uv缓存、pytest/mypy/ruff缓存、工作代码与样本脚本的字节码、旧覆盖率数据及不包含最新修改的dist包。

GT78原APK作为提取缓存，在记录来源与SHA-256后清理；Android XML、排序模板、设置及差异资料全部保留。原第三方工具和references中的APK不属于本次删除范围。

明细见[jobs/cleanup-20261012.json](../jobs/cleanup-20261012.json)。本次没有运行测试、lint、类型检查、构建或操作设备，没有删除运行环境、真实ROM/媒体、来源清单或导出证据。

研究缓存清理后，历史报告仍保留；重现时按[开源评估](OPEN_SOURCE.md)的来源及版本重新获取，不将旧绝对路径当成当前配置。

必读入口为[代码README](../README.md)、[STATUS](../docs/engine/STATUS.md)及所需功能说明。测试数据和历史检查器见[test_data说明](../test_data/README.md)，执行这些检查仍需用户批准。
