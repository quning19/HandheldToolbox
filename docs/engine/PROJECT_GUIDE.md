# 游戏库转换业务说明

更新日期：2026-10-16。当前业务入口为 `python -m library_converter`，GUI 汇总调用；保留的 `python -m retrolibx.cli` 是通用引擎及原 Android 任务入口。前者的电脑转换会处理完整平台配置，不能与原引擎普通 convert 的行为混为一谈。拆分前的详细模型、旧目录和选型过程见 [历史说明](archive/guides/2026-10-16-project-guide-before-split.md)。

## 导入、计数和选择

来源为 Pegasus/天马 G metadata 和真实文件，自动识别编码。metadata 可大于实际已安装 ROM 范围；只把实际存在且有关联资料的独立启动入口计入数量。一个游戏多个版本各自导出，多轨光盘描述文件的从属轨道不额外计数。缺失引用和未关联 ROM 分别提示，不改原始资料、不猜测游戏信息。

相对 ROM 引用以 metadata 目录为准，不缩短子目录或按同名文件补找；旧绝对路径迁移仍保留。封面只判断有效文件是否存在，不比较旧媒体内容。显式媒体及天马约定见 [来源规则](SOURCE_PROFILES.md)。

## 增量、全量与列表合并

Windows 业务默认按平台和 ROM 相对路径与已有 gamelist 比对：已有入口跳过，新增入口处理。全量替换会重新处理所选平台当前识别到的入口及媒体，不清空目标，也不删除旧额外条目。来源 ROM 移动/改名视为新路径，不自动转移统计。

转换引擎统一使用 merge_gamelists：旧非空 name、desc、sortname、favorite、playcount、lastplayed、altemulator 等字段保留，空字段补齐、新入口追加，旧额外游戏/文件夹/未知 XML 字段保留。相同路径重复或越界报错，不猜测合并对象；计划和发布保留基线保护及旧文件备份。该合并不是游玩统计求和，也不保证 XML 排版和编码逐字节不变。

新列表保持来源游戏与 ROM 展开顺序，游戏 sort/sort-by 映射到 sortname，旧非空排序仍优先。平台排序及相同键的版本显示次序不在本次改造范围。普通 Pegasus 的原始自定义字段可留在模型中，不代表全部写成 ES-DE 字段。

## 媒体与平台

游戏媒体只处理封面、Logo、视频，按 ROM 相对目录/文件名建立 ES-DE 布局；同游戏多版本共享的源封面会生成各版本副本。ROM 留在原目录，游戏媒体不缩放或转码，不处理 mini。子目录封面从内部实际游戏的有效封面选取，不增加游戏条目。详见 [Android 与文件夹封面](ANDROID.md)。

共用素材默认关闭；开启后先核对副本，再局部更新原 metadata 并清理允许迁移的源媒体，保留仍被其他字段引用的素材。详见 [共用素材](SHARED_MEDIA.md)。主题插画角标生成属于另一个工具，不受游戏媒体“不加工”的限制。

平台四文件基线在 `src/frontend_platforms/custom_systems-PG/`，不依赖相邻主题工程。新目标完整初始化，已有配置保留用户节点和命令、补齐所需平台。用户平台升级合并见 [统一平台](PLATFORMS.md)。

## 设备与启动边界

设备 ES-DE/媒体根、ROM 根和授权序列号使用当前发现或明确配置；历史报告不是当前路径配置。capture/build/deploy/publish 分工、C2/C4 上传和 XML 发布保护见 [Android](ANDROID.md)。设备索引零字节占位文件不是真实媒体，不能拿去执行普通复制转换。

GBA vib 等启动确认、已支持的 metadata 启动命令转换见 [来源规则](SOURCE_PROFILES.md) 和 [Android](ANDROID.md)。不执行来源 launch，不按文件名猜核心，不擅自改变现有启动配置。显示、实际启动、震动及设备写入按用户授权验收。

当前测试结果集中维护在 [STATUS](STATUS.md)，未来工作在 [PLAN](../PLAN.md)。原 [review 处理记录](REVIEW-2026-10-12.md) 仅说明历史问题处理；旧测试数字不代替今天的测试记录。
