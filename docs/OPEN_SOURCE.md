# 开源项目复用评估

2026-10-12。范围：搜索天马/Pegasus元数据到ES-DE列表与媒体的开源实现，核对源码、许可证、依赖及真实样本。用户允许第三方依赖，主要目标是减少本仓库维护量。

## 结论

本轮找到可修改的相关仓库，但没有一个已经验证可以原样满足全部要求。初轮按单向天马G到ES-DE评估，倾向局部复用；用户进一步明确多目标导出与天马自身优化后，**建议以RetroLibX核心为扩展基础，保留现有分层，逐步补齐具体适配器。** 原版样本失败属于实现缺口，不足以否定通用模型架构。无需继承完整ROM管理器、刮削器或GUI。

| 候选 | 已核对的用途与授权 | 本项目判断 |
|---|---|---|
| [tiancheng91/retrolibx](https://github.com/tiancheng91/retrolibx) | Python多前端转换库，有MIT全文及PyPI发行；支持Pegasus/ES-DE | 最接近目标，允许按MIT复制/修改；原版未通过真实样本，必须补天马与ES-DE适配 |
| [mcpalmer1980/pegasus-tool](https://github.com/mcpalmer1980/pegasus-tool) | Python脚本，可导出gamelist；约1903行，GUI用PySimpleGUI，图片功能用pygame；根目录及源文件未见明确许可证 | 可查阅功能，暂不作为授权源码复制；GUI与操作流程耦合，改造不一定比小工具省事 |
| [freefrank/ModernRetroRomManager](https://github.com/freefrank/ModernRetroRomManager) | React/Rust/Tauri完整ROM管理器，解析file/files；README声明MIT，目录树未发现主程序LICENSE全文 | 有参考价值，但完整fork会扩大工程；复制前还需核实完整授权，未实测其导出 |
| [valsou/bellerophon](https://github.com/valsou/bellerophon) | Python、GPL-3.0，EmulationStation列表生成Pegasus元数据 | 主要转换方向相反，不适合作为首版基础 |
| [Gemba/skyscraper](https://github.com/Gemba/skyscraper) | Qt/C++、GPL-3.0，刮削/缓存后输出ES-DE与Pegasus | 可以fork，但本项目不需要其刮削、缓存和编译体系，不建议引入 |

另核对了[Pegasus官方转换网页](https://pegasus-frontend.org/tools/convert/)：可手工转换文本，但网页说明不足以证明其能处理媒体复制、既有列表合并和掌机任务包，不能当作完整替代方案。[官方工具入口](https://pegasus-frontend.org/tools/)

本地封面工具的说明没有给出可核对的源码仓库；本轮也未找到能确认与本地EXE版本一致、含主程序许可证的仓库。保留为历史参考，不反编译后当作可维护源码。

## RetroLibX真实样本结果

测试发行版0.1.0，MIT版权声明为2026 tiancheng91。要求Python>=3.12，声明依赖为lxml、platformdirs、pydantic、PyYAML、rich、typer。[发行与依赖要求](https://pypi.org/project/retrolibx/0.1.0/)

用当前原包节选分别调用Pegasus导入和ES-DE渲染，XML只在内存中生成，没有调用文件执行器。全部58个输入文件前后SHA-256一致。

| 平台 | 预期ROM | 实际导入ROM/生成game | 生成的媒体复制目标 |
|---|---:|---:|---:|
| GBA | 12 | 2 | 0 |
| GBA hack | 1 | 1 | 0 |
| GBA vib | 2 | 2 | 3 |
| 合计 | 15 | 5 | 3，且布局不符 |

源码确认的缺口：

- Pegasus导入只取record.get("file")，忽略files，红宝石和两组细胞分裂被告警后跳过。
- 解析器把空行当作记录边界，本样本中部分媒体字段未附着到game记录；没有按天马标准游戏media目录补齐素材。
- ES-DE适配器继承通用EmulationStation导出，把媒体写成images/游戏-box_front.png等，未生成downloaded_media/system/covers、marquees、videos布局。
- 通用导出每个game只有首个ROM进入XML，额外ROM只有文件请求；使用ROM basename，子目录也被去掉。
- 没有本项目需要的掌机脚本与自定义Android系统配置发布；既有配置保护仍需补充。

关键文件的当前GitHub提交f1a73c126ba450ae7d01a856e17ed7aad83eeff9与实测发行版逐字节一致，不能认为这些缺口只存在于旧版。[Pegasus适配源码](https://github.com/tiancheng91/retrolibx/blob/f1a73c126ba450ae7d01a856e17ed7aad83eeff9/src/retrolibx/adapters/pegasus/adapter.py)、[通用导出源码](https://github.com/tiancheng91/retrolibx/blob/f1a73c126ba450ae7d01a856e17ed7aad83eeff9/src/retrolibx/adapters/emulationstation/adapter.py)

因此，**MIT授权方面可以复制或fork，功能方面不能直接运行后当作完成**。可复用候选是其XML读写、数据模型、路径索引与规范化函数；需要按本项目字段保留规则核对，不能默认通用模型完整保存ES-DE所有字段。

原始测试证据：[retrolibx-0.1.0-assessment.json](../test_data/research/retrolibx-0.1.0-assessment.json)。wheel校验SHA-256为83a8b6ffd8ad05053363e35054938bdba5e89f9c5d31e93d035e4131766c5d11，与PyPI声明一致。测试使用已有的Python 3.12运行环境，缺失PyYAML安装在项目忽略缓存，没有更换用户系统Python。

## 更新后的实现选择

1. 优先保留RetroLibX的适配器、通用模型、导出意图、操作计划和执行器分层，固定上游版本，补Pegasus与ES-DE适配及掌机执行。
2. 根据修改位置选择依赖加适配或fork；涉及解析器与核心字段修正时fork是合理选项，保留完整版权、许可证和提交来源。通用模型保留一游戏多个ROM，按目标格式决定是否展开，天马特有字段不在导入时丢弃。
3. 不硬性限制纯标准库、Python版本或文件数；按实际维护成本选择CLI/XML/校验库。使用完整RetroLibX时需Python 3.12+，不为了维持3.9而回改其整套代码。
4. 复制、fork或包依赖都要先通过12-ROM/36-media，再通过15-ROM/45-media；现有资料保护与VIB启动要求不因复用而省略。

用户已确认基于RetroLibX实施；产品代码位于../retrolibx，已修正本页记录的原版缺口。尚未创建线上fork或安装完整应用。原版评估作为选型证据保留，当前验证见[实现记录](IMPLEMENTATION.md)；其他候选仍仅做文档/源码检查。

2026-10-12资料整理：本页为选型时的原版评估，当前实现看[STATUS](../docs/engine/STATUS.md)。候选源码与研究依赖的临时副本.deps/research已清理，评估JSON及来源链接保留；历史绝对路径不作为当前运行配置。
