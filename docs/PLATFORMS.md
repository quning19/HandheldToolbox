# 共用平台配置

具体目录、模型及保留边界见[项目说明](PROJECT_GUIDE.md)，已修复及暂缓事项见[review处理状态](REVIEW-2026-10-12.md)。

最终完整平台XML基线是FrontendThemeConverter/source/configs/custom_systems-PG目录，包含es_systems.xml、es_find_rules.xml、es_import_rules.xml、es_systems_sorting.xml四个文件。2026-10-12通过ADB只读对比，四文件与RP6逐字节及SHA-256一致，系统表含76个平台。本项目在[共用模块的完整配置目录](../src/frontend_platforms/custom_systems-PG)保存该版本的发布副本。

识别、母体及角标信息位于[platforms.json](../src/frontend_platforms/platforms.json)，识别与配置读取位于[frontend_platforms](../src/frontend_platforms/__init__.py)。JSON version 2仅保存配置来源、别名、母体、类型、角标及主题显示名，不再重复维护XML定义。模块只用标准库，兼容Python 3.9，游戏转换与FrontendThemeConverter共用。XML基线不是历史废弃配置，不按某次导出平台筛选裁剪。

76个定义在运行时直接读取FrontendThemeConverter已验证的source/configs/custom_systems-PG/es_systems.xml；系统名、ROM目录、主题、platform、扩展名、命令正文、标签及顺序来自同一XML。七个主题批次重复的九个平台母体、角标和主题显示名已抽出；主题槽位、布局和处理范围留在原主题项目。

JSON明确声明本地XML目录及独立安装用的发布副本目录。两个工程本地使用主题工具基线；主题工程通过paths.system_config明确提供目录。主题工具未安装时可使用声明的发布副本；主目录部分文件缺失、显式目录不存在或补充信息引用不存在的平台均报错。发布副本仅在发布时从维护基线更新，不手工维护第二套定义。HandheldConfig.platform_config_dir和convert --platform-config-dir可指定其他完整四文件目录，同时影响平台识别和XML读取。

| 内部平台 / 系统名 | ROM目录 | 主题资源名 | 母体 |
|---|---|---|---|
| gba | GBA | gba | — |
| GBA HACK | GBA hack | GBA hack | gba |
| GBA vib | GBA vib | GBA vib | gba |
| wii | WII | wii | — |

XML的name是内部平台标识，不再另建gbah/gbavib。运行时的rom_directory与theme从XML各自读取实际名称，不能由name大小写转换推导。SystemRegistry优先加载共用定义；systems.yaml保留上游其他前端的映射与别名，不能替代共用平台名称。

识别优先匹配真实metadata目录，再匹配shortname与collection；按明确配置识别Hack及母体，不将未知的带hack字样的名称猜成已知平台。括号属于名称的一部分，MD hack与MD hack(picodrive)独立识别。系统名允许空格和括号，但拒绝路径分隔符、控制字符和越界语法。

systems_template可省略，默认使用完整76平台XML；外部模板只覆盖其中相应定义，不能使全局配置缩减为单平台。构建任务保留完整系统表和其他三个完整规则文件，仅对所选游戏数据及必要ROM路径进行处理。现有主题、命令、用户字段及额外系统保留。system_ids只改变输出系统名，内部平台标识保持不变。

FrontendThemeConverter通过config/project.json的paths.platform_config指向共用识别配置；system_config指向最终完整XML基线。批次只保存name、厂商、action、slots及主题特有回退/说明；theme/source/badge_text/system_name加载时补齐，冲突时报错。

GBA vib节点始终保留；天马来源规则默认要求该平台明确确认，未确认时仍输出完整配置与所选列表预览，仅阻止生成apply.sh。确认不绑定核心文件名，也不强制改动已验证的命令；来源规则位于[SOURCE_PROFILES.md](SOURCE_PROFILES.md)。不据此声称设备震动效果已验收。

2026-10-12用户新增全局规则：执行测试须事先批准，默认只做静态代码review；小改动不自动触发全量测试。项目文档中的测试命令仅作参考，不代表自动执行授权。
