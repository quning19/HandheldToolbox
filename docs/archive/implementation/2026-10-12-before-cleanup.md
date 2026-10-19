# 实现与验证记录

2026-10-12。代码位于[retrolibx](../../../retrolibx/README.md)，保留上游通用模型与五层流程。本地分支frontend-trans-tool，上游为f1a73c126ba450ae7d01a856e17ed7aad83eeff9；未提交、推送或创建线上fork。

## 已实现

- 以FrontendThemeConverter已验证的76个系统定义为基础抽出共用平台配置与识别模块，两个工具共同加载；内部使用GBA HACK/GBA vib，ROM和主题名分别保留GBA hack/GBA vib，不再创建gbah/gbavib内部平台。见[共用配置](../../../retrolibx/docs/PLATFORMS.md)。
- Pegasus file/files、注释、空行、混合换行、显式编码、继承launch、来源字段保留；平台选择与子平台边界。
- 游戏保持多个ROM和共享素材，在ES-DE导出时逐ROM展开，保留子目录与正确媒体名称；缺ROM/冲突阻塞，缺媒体告警。
- 原包错误媒体引用在当前游戏目录唯一定位并报告，不修改源文件。
- 已有gamelist补空字段与新增条目，保留其他记录及用户字段；系统路径匹配时复用标识、主题和命令；自定义绝对媒体目录与设置一致性核对。
- scan/build/capture入口，基于同一ConversionPlan生成离线apply.sh；批量ADB只读取metadata、索引和XML。
- 临时媒体复制、已有文件保留、配置基线检查与备份、失败停止、重跑；GBA vib特殊核心缺少明确确认时只输出预览。

使用说明见[Android使用](../../../retrolibx/docs/ANDROID.md)。任务包的plan.json用于核查，不替代一个可编辑计划协议。普通上游命令保留，以便后续多前端扩展。

## 验证结果

| 范围 | 结果 |
|---|---|
| 真实普通GBA节选 | 5条游戏→12个ROM、36个媒体目标，逐路径与源素材绑定核对 |
| 真实三平台节选 | 8条游戏→15个ROM、45个媒体目标；VIB资料/媒体导出通过，启动未确认 |
| 原ZIP普通GBA整库索引 | 484条游戏→503个ROM、1509个媒体；估计媒体输出1,574,102,682字节 |
| MuMu Android 15 | 序列号127.0.0.1:16384，GBA+Hack复制39个媒体，源/目标SHA-256全部一致 |
| MuMu重跑 | 复制0、保留39；已有媒体内容不在普通重跑时重复校验 |
| 配置外部变化 | 修改独立测试gamelist后脚本在复制前停止；测试修改已恢复 |
| 中断 | 在复制临时文件时注入SIGTERM，返回130；目标无媒体半文件及配置，重跑完成36个媒体 |
| 设备读取 | 读取45个文件索引、2份metadata、3份目标XML，未下载ROM/媒体正文 |
| 自动测试（当前） | 45通过、0跳过；符号链接导出用例已取消，创建分支和link别名排除出覆盖率；覆盖率87.90% |
| 质量与构建 | Ruff、格式检查、strict mypy、git diff --check、wheel/sdist构建通过 |

整库验证只读取ZIP目录及metadata，使用占位索引，未解压整库ROM/媒体，也没有在MuMu执行503-ROM任务；不代表整库实际内容校验或性能验收。

来源节选的[manifest](../../../test_data/original_excerpt/manifest.json)保持不变。结构与逐文件证据：

- [真实样本映射与媒体SHA-256](../../../test_data/research/python-fixture-results.json)
- [MuMu执行证据](../../../test_data/research/mumu-python-implementation.json)
- `jobs/gba-full-plan/summary.json`为整库预览；`jobs/mumu-catalog-final/`为最新只读设备索引。

此前用户安装ES-DE后，曾向/storage/emulated/0/ES-DE写入frontendtrans_gba与frontendtrans_gbah测试系统的gamelist、媒体，以及custom_systems/es_systems.xml中的两个测试定义。原有普通GBA资源未作为转换输入，未由工具修改。工具未安装应用。

用户已明确由其负责视觉与实际启动验收。本次重跑只检查文件，输出到/storage/emulated/0/Download/FrontendTransTool-test/ES-DE-retest-20261012-02；未操作ES-DE界面。本次前后核对58份源样本和现有正式ES-DE全部文件哈希，均未变化。

本次产出与证据位于jobs/retest-20261012-01/retry：

- local-all/：三平台15个ROM条目、45个实际媒体文件；local-gba/：12个条目、36个媒体。ROM仍引用源目录。
- task/：设备输入捕获后生成的13-ROM/39-media任务；catalog/仅含metadata、索引和零字节资源占位。
- [本次设备结果](../../../jobs/retest-20261012-01/retry/device-results.json)：39个媒体哈希全部一致，XML与任务正文一致；重跑复制0，配置变化提前停止；SIGTERM返回130、无半文件，恢复后36个媒体哈希全部一致。
- [本次本地结果](../../../jobs/retest-20261012-01/retry/preparation.json)：普通GBA及三平台XML逐ROM路径、全部媒体哈希、dry-run零写入、VIB缺确认阻塞均通过。

新增ES-DE原生settings/es_settings.xml兄弟节点格式、显式系统标识及已有系统复用回归用例。Ruff、格式、strict mypy、git diff --check与新wheel/sdist构建均通过。首次测试报告读取遇到Windows默认GBK编码错误，修正为显式UTF-8后在新独立目录重新完整运行通过。

用户随后确认符号链接不属于本项目需求：测试不再收集该导出用例，保留普通复制及其他现有测试；只排除符号链接创建与link别名的6行，不排除路径安全检查或整个执行器。覆盖率口径调整后的完整测试与构建通过，转换行为及上述产出目录未变。

## 尚待验收

MuMu已安装ES-DE 3.4.1-58；此前有过列表/媒体显示检查，后续由用户自行验收视觉效果与实际启动。普通/Hack启动、VIB震动核心及断开电脑后的手动终端权限尚未验收。软件文件检查不等于整个首版产品已验收。

同文件多个collection暂明确报错；自定义媒体目录中的未解析变量/相对路径暂报错。Pegasus回导不保证原文排版/注释/编码往返。封面缩放、完整断点账本、原地天马优化按方案后移。

## 主题平台统一（2026-10-12）

主题工具的原系统XML是独立文件，但母体、角标和显示名分散在七个批次。现已将76个定义和九个平台批次共性抽到retrolibx/src/frontend_platforms/platforms.json，并提供Python 3.9兼容的纯标准库识别模块。两个工具加载同一文件，七个批次只维护处理范围与主题特有槽位。源主题、原系统XML和dist主题产物未重建。

全局批准规则生效前完成：本项目49项完整测试通过、0跳过，共用模块参与覆盖率统计88.00%；主题项目13项测试在自带Python 3.12环境通过；Python 3.9已做共用模块识别验证。主题Python 3.9环境原本缺Pillow，已将依赖准备在当前工作区.deps/theme-tests-py39，全局规则生效后未继续执行其测试。

[平台对齐记录](../../../jobs/platform-alignment-20261012/results.json)核对76个系统的全部字段及命令顺序、七个批次加载后的平台规则，均保持原语义；真实节选15个ROM路径和45个媒体哈希通过。新[样本产出](../../../jobs/platform-alignment-20261012/output)使用gba、GBA HACK、GBA vib目录；任务包13-ROM/39-media的系统字段与原主题配置一致，VIB缺核心确认仍阻塞。

规则生效后只做静态review及文档整理，未再运行测试、lint、类型检查或构建。现有dist wheel/sdist属于此前源码构建，不代表后续字段顺序/识别小改动已重新打包。此次未操作设备界面，也未执行新设备任务。

## RP6完整配置确认

2026-10-12。当前设备序列号已脱敏，ROM根目录/storage/<SD_VOLUME>/Roms（存储卷标已脱敏），ES-DE目录/storage/emulated/0/ES-DE。主题工具source/configs/custom_systems-PG内四个XML与RP6/custom_systems逐字节一致，SHA-256一致，双方均76个平台。该目录确认作为最终完整基线；此前将其称作历史参考不准确。

[完整配置副本](../../../jobs/rp6-complete-config-20261012/custom_systems)与[对比记录](../../../jobs/rp6-complete-config-20261012/comparison.json)已保存在电脑。掌机只读，未写入、安装或启动应用。

生成逻辑改为总是保留完整系统表及查找/导入/排序三个完整规则文件，选择平台仅限定游戏列表和媒体。已有配置及额外系统保留；VIB未确认时保留完整预览，只阻止apply.sh。为完整配置调整了现有回归用例，但遵循新全局规则未执行测试、lint、类型检查或构建，当前只完成静态review。

线上fork不阻塞本地开发。用户提供fork链接后，可把它设置为origin，保留upstream指向原仓库；本轮未进行任何线上写入。

## 平台来源与列表统一（2026-10-12 后续）

用户确认实施平台来源统一与列表合并统一，排序暂不修改，天马特定规则先解释。platforms.json改为version 2，仅保留来源路径、别名、母体、类型和角标等补充信息；目录、主题、扩展名及完整启动命令从主题工具已验证XML实时读取。未安装主题工程的独立环境使用声明的发布副本。显式platform_config_dir缺失及部分配置缺失会报错，不静默回退。

主题工具tools/common.py明确传入system_config所在目录；游戏转换配置新增platform_config_dir，普通convert新增--platform-config-dir，平台识别与XML生成共用来源。原四个XML、排序策略和主题素材未修改。

普通ES-DE convert与Android build共用merge_gamelists，以ROM相对路径保留已有非空字段、补空及追加新条目，同时设置原文件哈希和备份。普通convert不额外生成Android系统配置；ROM/媒体冲突策略保留。新增5个相关测试用例，未执行任何测试、lint、类型检查、构建、导出或设备操作；现阶段仅完成代码及静态review，原有通过记录不代表本次变更已经实测。

## 来源规则配置与获批测试（2026-10-12 后续）

用户随后批准上述五个用例，并要求加入天马来源规则。新增profiles/generic.json与profiles/pegasus-g.json，媒体目录及文件名、developer版本说明处理、需确认的平台名单从配置读取。Android默认天马G规则，普通命令默认generic，支持source_profile/--source-profile显式文件。原始metadata保留，规范化进入IR，ES-DE适配器不再判断Pegasus developer前缀。排序策略未改变。

VIB按配置平台名单要求确认，确认后保持已有/基线的完整命令及顺序，不再要求gpsp_rumble文件名或强制launch_overrides。实际震动功能仍待用户验收。

用户另行批准三个来源规则用例。执行结果：tests/test_service_cli.py新增3个用例、tests/test_platforms.py新增2个用例、tests/test_source_profiles.py的3个用例，合计8/8通过。覆盖已有列表保留与基线保护、统一XML加载、媒体回退及显式路径优先、版本说明与原字段保留、VIB确认与多命令保留。全部为本地临时数据，未执行全量回归、覆盖率、lint、类型检查、构建、真实库导出或设备操作。其他已有测试未扩大执行，当前dist仍为旧包。
