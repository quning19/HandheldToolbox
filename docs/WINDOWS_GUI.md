# Windows 图形界面

更新日期：2026-10-15。显示方案保持用户确认的 Fluent 工作台，采用 PySide6 / Qt Widgets / QFluentWidgets。界面基线保存到标签 baseline/windows-ui-20261015，实际业务在 codex/windows-business 分支接入。

## 打开

本机项目虚拟环境已准备核心依赖、PySide6 6.12.0、PySide6-Fluent-Widgets 1.11.3 和 Pillow 12.3.0。双击项目根目录的“启动界面.cmd”。源码入口：

~~~powershell
& '.\retrolibx\.venv\Scripts\python.exe' -B '.\launch_gui.py'
~~~

其他机器需要 Python 3.12+；在项目根目录创建虚拟环境后安装完整桌面依赖：

~~~powershell
python -m venv retrolibx/.venv
& '.\retrolibx\.venv\Scripts\python.exe' -m pip install './retrolibx[desktop]'
~~~

ADB 从 PATH、ANDROID_HOME、ANDROID_SDK_ROOT 或当前用户 Android SDK 安装目录查找，未找到时报错。未打包独立 EXE。应用启动不自动连接设备或扫描 ROM；用户点击具体操作才执行对应业务。

## 游戏库转换

- 掌机来源先点击“刷新设备”：要求恰好一台已授权设备；识别内置存储和 SD 卡里的 rom/roms（不区分大小写），只统计候选目录直接子目录数。多设备在线或 ES-DE 位置有歧义时报错，不猜测目标。
- Windows 下没有在线设备、也没有待授权设备时，刷新会寻找正在运行的 MuMu，通过其同目录 MuMuManager 的只读 info 命令取得已启动安卓实例的本机 ADB 端口，再连接并重新读取设备列表。不写死安装位置或端口，不启动模拟器，不扫描网络；已有在线设备时直接使用。未授权、离线及多设备分别给出提示。当前自动连接仅支持 MuMuNxMain / MuMuManager 这一安装形式。
- ES-DE 默认识别内置存储根目录里的 ES-DE；新设备没有该目录时使用 /storage/emulated/0/ES-DE，实际转换时初始化。刷新设备不扫描平台内容。
- 选择来源后点击“加载平台”才读取 metadata 和文件索引。工作线程逐平台追加卡片；修改来源会取消旧加载并隔离旧结果。主动取消时已完成的平台可继续选择。
- 电脑来源按当前绝对路径自动分配 library/<来源目录名>-<路径标识>/ES-DE，避免不同来源的同名 ROM 被误认作已收录；不需要单独设置输出目录。
- ROM 数量按实际存在的独立启动入口计数；多版本分别计数，同一封面按各版本文件名复制。cue/gdi/m3u/ccd 所引用的轨道或从属文件不重复计数。只统计封面覆盖率。
- 缺失引用、未关联资料的 ROM 和无法处理的平台显示在卡片提示中；缺失引用不转换，不改写或“修复”源 metadata。平台解析错误保留失败状态。
- metadata 自动识别 UTF-8（含 BOM）、带 BOM 的 UTF-16 和 GB18030。不同平台编码可一并选择，不提供编码设置。
- 默认只处理已有 gamelist 中没有的 ROM 相对路径；不比较旧素材时间、大小或内容变化。“全量替换”重新处理所选平台现存入口并覆盖对应素材，保留额外条目及已有收藏等用户字段，不清空目录。
- 共用素材默认关闭。明确开启后复用已有的副本验证、metadata 局部发布和源素材保护流程。已迁移到 ES-DE 的素材可用于后续新增版本，ES-DE 目录里的源副本不作为清理对象。

掌机一次批量捕获文件名/大小索引、metadata、光盘描述文件和已有 ES-DE 文本配置，不下载 ROM、图片或视频。已共用素材的绝对引用在实际 MediaDirectory 内批量读取存在信息，使用本地空文件表示路径；设备内复制仍使用真实路径。扫描到的空文件不能当作真实资源导出。

转换复用 Adapter → Library → ExportIntent → Planner → Executor。掌机一次 build 生成所选多平台任务，复用 deploy/upload/publish 执行媒体复制及配置发布；遵守 C2/C4 上传约定。设备 MediaDirectory 遵循 ES-DE 设置，缺失系统配置初始化完整四文件；已有配置保留节点、启动参数和伴随规则，补齐缺失内容。GBA vib 沿用既定 metadata 启动转换，不套用普通 GBA 核心。

完成转换后必须重新加载平台再执行下一次，以取得新的发布基线。设备 XML 备份采用基线摘要区分版本，避免后续增量转换与旧备份冲突。电脑目录模式生成本地媒体、列表及平台配置，不配置 Windows 模拟器或宣称可以直接在 Windows ES-DE 中启动游戏。

## 主题适配

列表按七套已支持的主题显示本地原版、转换结果、设备主题状态：Canvas、Aura、Alekfull NX、Elementerial、Iconic、iiSU Interpreted、PlayStation-X。

1. “同步原版”从当前设备的 ES-DE/themes 读取真正的原版主题，按 capabilities.xml 识别，下载到 themes/original/<主题标识>；已适配的“_天马G”主题不会被当作原版。设备不存在原版时报告缺失。也可手动将已有原版主题目录放入 themes/original，然后刷新列表。
2. “转换主题”使用本地原版和统一平台定义，生成完整主题到 themes/exported/<原主题名>_天马G。七套槽位规则、目录素材、专用图优先、母体回退、角标和 androidgames 比例处理从原主题工程整理进本项目，不依赖相邻工程路径。
3. “上传主题”只接受具有成功生成记录、原版标记和当前平台定义摘要的完整结果，使用 C2 上传到自动识别的 ES-DE/themes；上传后自动刷新状态。
4. “刷新设备主题”只读取主题目录和 capabilities.xml，不下载素材或计算整套主题哈希。读取失败保持“未检查”，“已存在”仅表示对应主题存在。

原有主题批次对现有分类的处理范围保持；新增独立分类按该主题的全套槽位从母体生成，沿用母体模式直接复用母体主题名。缺少必需素材会阻止本次结果进入可上传状态，不承诺任意主题或平台均可适配。

转换先在工作目录临时区生成完整结果，成功后再替换管理的导出目录；先前版本保留在对应 temp 任务下，失败不会用不完整主题覆盖旧版本。平台定义变更会使旧结果过期，需要重新转换。

## 平台管理与保存位置

默认平台列表来自维护的完整 XML，另包含已讨论的 PSP Minis。已有界面阶段保存的平台定义继续读取，不擅自覆盖。平台管理中的添加、编辑、删除供游戏库及主题两边使用；新分类需选择母体以继承完整启动模板。添加的平台可自动参与识别和对应主题资源生成。沿用母体主题名不应使母体平台识别变为歧义。

执行文件同级 settings.json 保存唯一工作目录及 light/dark 外观，不使用 AppData。工作目录：

~~~text
config/platforms.json       用户平台定义
config/theme-results.json   成功的主题生成记录
themes/original/            本地原版主题
themes/exported/            完整适配主题
library/                   按电脑来源隔离的转换结果
devices/                   预留的设备资料目录
logs/desktop.log           后台任务失败明细
temp/                      目录索引、配置快照、任务、中间文件及先前主题副本
~~~

每个业务任务在 temp 下保存独立目录。捕获、发布使用的临时文件也放在该工作目录。当前保留这些任务便于失败后定位和恢复，不自动删除用户产物。生成的运行时平台四文件来自维护基线与用户覆盖，属于产物；不另建一套手工维护的平台 XML。

## 界面与线程

窗口默认 1140 × 750，最小 1000 × 650；Windows 原生标题栏与边缘缩放，切页保持窗口尺寸。固定侧栏 184px，平台网格行列间距 12px。卡片沿用 Canvas 方形素材，上部图片铺满、名称居中描边，下部显示实际计数。

设置提供即时亮暗切换并保存。亮色雾蓝/白色，暗色深蓝灰，蓝紫为强调色、青绿为完成状态；微软雅黑 UI 优先，页面标题 24px、区块标题 17px、正文 14px、辅助文字 13px。选中样式和键盘焦点区分，鼠标操作不留下其他页面的焦点框。

两个主页面的底部反馈区均固定 72px 并保留隐藏空间，不因进度显示、完成或取消挤动列表。长消息省略，悬停可看全文。

一个后台任务入口协调设备识别、扫描、转换与主题操作；忙碌时锁定冲突操作及平台/工作目录修改。可取消阶段在阶段边界响应；设备复制、发布或一次完整主题上传开始后不强行终止，界面暂时隐藏取消按钮。关闭窗口时先等待安全结束，不销毁仍在工作的线程。后台错误写入日志，并在原页面显示。

## 源码

- gui/app.py：窗口、导航、设备状态；gui/appearance.py：亮暗主题；gui/tasks.py：线程生命周期与任务互斥。
- gui/library_page.py、themes_page.py：界面事件与结果展示；settings_page.py、state.py：设置及平台管理。
- application/desktop.py：来源识别、平台检测、桌面转换编排；selection.py：实际入口与增量筛选。
- application/platform_catalog.py：完整配置基线与平台覆盖；themes.py、theme_badges.py、theme_data/：主题业务与既有规则。
- application/device.py、handheld.py、deployment.py、publication.py：复用的捕获、任务生成和设备发布。
- gui/assets/platforms/：既有演示的 Canvas 缩略图副本。

## 当前审阅及测试边界

MuMu 自动连接是此前 29 项通过后新增的修复。用户单独批准后，对 d48f9fd 执行 test_desktop_discovery.py 的 10 个模拟用例及原有设备识别用例，共 11 项，一次全部通过（0.26 秒），无失败或复测。仅模拟进程和 ADB，没有连接设备、启动窗口或执行其他测试。报告见 [JUnit](../jobs/mumu-discovery-check-20261015/initial.xml) 和 [范围记录](../jobs/mumu-discovery-check-20261015/result.json)。窗口与实际自动连接仍由用户操作验收。

按用户要求已向当次连接的 MuMu 内置存储 /storage/emulated/0/ROMs 上传 23 个演示输入文件，准备前该目录没有平台子目录。GBA 预期 4 入口/3 封面，GBA hack 4/4，PS1 3/3；包含中文空格、多版本共用封面、嵌套目录、cue 多轨和三种 metadata 编码。ROM 为不可启动的占位文件，图片复用项目已有 Canvas 平台缩略图。这里只准备并上传数据，未通过新代码扫描或转换，未修改 ES-DE 配置或主题。准备资料见 workspace/temp/emulator-demo-20261015，上传记录见 jobs/emulator-demo-20261015/result.json。

业务接入后先完成静态源码和 diff 审阅及依赖准备。2026-10-15 用户批准此前列明的 29 项本地测试，并指定窗口操作由用户完成。对提交 2c4a2df 执行一次，29 项全部通过，耗时 5.09 秒，无失败、跳过或修复复测。报告见 [JUnit](../jobs/desktop-business-check-20261015/initial.xml) 和 [范围记录](../jobs/desktop-business-check-20261015/result.json)。

通过范围为 test_desktop_business.py 的 19 个业务用例、test_gui_state.py 的 3 个主题配置用例，以及 7 项受影响的既有局部回归。业务用例覆盖真实计数、增量/全量、共用迁移后新增、多轨、混合编码、平台继承、Android 媒体来源边界/备份、主题生成/过期/失败保留及模拟设备捕获。全部只使用临时数据和模拟 ADB，没有启动窗口、连接真实设备或模拟器，也没有更改真实资源。

该建议的既有用例精确范围：test_gui_state.py 中 theme_persists_across_reopen_and_workspace_change、theme_save_failure_keeps_previous_mode_and_file、older_settings_without_theme_default_to_light；test_shared_esde_media.py 中 shared_migration_updates_in_place_after_all_rom_copies_and_keeps_mini、changed_metadata_or_differing_target_stops_before_source_mutations、failed_copy_never_publishes_source_metadata_or_cleans_sources，以及 android_shared_migration_is_opt_in_and_build_does_not_change_source 的关闭/开启两项；test_handheld.py 中 build_uses_ir_and_plan_without_copying_media；test_platforms.py 中 platform_registry_rejects_ambiguous_aliases_and_invalid_bases。上述名称均以 test_ 开头，此处为便于阅读省略前缀。

本次没有执行 lint、类型检查、覆盖率、全量回归、构建或打包。后台服务用例通过不等于原生界面线程、真实设备读写和七套真实主题资源均已验收；这些仍需分别完成。历史界面阶段曾完成获批的八组交互检查及 6 个配置用例，窗口边缘拖拽、无引用平台的界面删除存在已记录边界；记录保留在基线标签及 jobs/gui-check-20261015。

核心上游 MIT 许可保留；QFluentWidgets 开源版 GPLv3 的发行约束和 Canvas/原主题素材的授权记录仍需随独立软件发行维护。此轮未打包或发布软件。
