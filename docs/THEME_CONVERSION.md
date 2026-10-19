# 通用主题适配

实现入口为 `src/theme_converter`，不按主题名字选择专用 profile。七套旧规则仅保留为开发回归对照，七套完整主题作为本地只读覆盖样本，均不随软件发布。

解析加载顺序参考 ES-DE 的 [ThemeData.cpp](https://gitlab.com/es-de/emulationstation-de/-/blob/master/es-core/src/ThemeData.cpp) 及[主题文档](https://gitlab.com/es-de/emulationstation-de/-/blob/master/THEMES.md)。解析器保存条件区域中的变量值，按变量、配色、字号、语言、include、view、variant、宽高比分阶段处理；相对路径以实际声明 XML 为依据，记录路径来源、分支和输出目标，避免把整个主题中的平台名称全文替换。

统一策略：已有目标素材优先；缺少时从母体继承；主题的默认机制继续保留。include 的平台资料会保留结构和其他变量，只调整明确的显示名字段。栅格插画、背景和控制器素材可使用统一角标；遮罩、渐变、字体、按钮、Logo 保持原样。SVG、视频和动画不转码；静态 JPEG/WebP 处理使用 quality=92。Android 封面/卡带比例继续参考同目录 Switch 元数据。

只加载实际引用的 XML，不把目录内未引用的模板和草稿当作运行输入。轮播/网格可沿用主题的文字回退；custom 图层有对应基础图层时允许留空，原版未提供的装饰覆盖层保持为空，均在报告中说明。主体素材及母体都不存在、且没有已支持回退机制时仍报告错误。

解析错误、越界路径、循环 include、无法展开的资源变量、用途不明或分支写入冲突写入本地 analysis.json，并阻止发布完整结果。报告留在可重建任务目录。解析器不渲染 ES-DE 画面，新的主题结构可能需要补充通用规则。样本覆盖和导出结果见 [解析测试](TESTS_INDEPENDENT_TOOLS_20261016.md)与[功能测试](TESTS_FUNCTIONAL_20261016.md)。

适配结果仍由 ES-DE 加载，用于天马G游戏平台目录，不生成 Pegasus QML 主题。设备上已有结果不代表拥有本地原版或有效生成记录。

生成记录包含：完整源文件内容摘要、源文件索引、输出索引、相关平台依赖、解析器版本、素材策略版本及报告路径。平时状态显示用本地索引快速判断；内容摘要按文件索引缓存，上传前重新读取本地源内容确认摘要，不为状态提示读取设备的大素材。新增仅沿用母体的分类不需要生成新主题文件，因此不因该新增项而过期。界面版本、ADB、亮暗模式和卡片风格不参与过期判断。

需要重新转换的结果仍保留，但不能上传。成功替换原版或输出前将旧目录移到 backups/themes，并记录原位置；失败时恢复旧位置。旧生成记录没有新版本/依赖信息时标记为需要重新转换。

## 官方主题目录和更新

参考 ES-DE [GuiThemeDownloader.cpp](https://gitlab.com/es-de/emulationstation-de/-/blob/master/es-app/src/guis/GuiThemeDownloader.cpp)，使用相同的 [themes-list](https://gitlab.com/es-de/themes/themes-list) 数据源，合并 `themes` 和 `themesAndroid`。保留作者、截图、比例、变体、配色和弃用信息；截图展示原版效果，收录不代表适配兼容性已验证。参考来源见 [ES-DE MIT 许可](licenses/ES-DE.txt)，主题自身许可随文件保留。

`catalog.py` 调用 PATH 中的 Git for Windows，不依赖相邻 ES-DE 工程。目录和预览保存在 `themes/catalog`，原版仓库在 `themes/original/official-<reponame>`，转换结果在 `themes/exported`。原版标记保存来源与提交，`config/theme-updates.json` 保存检查记录；旧导入和旧设备同步内容保留，不按名称自动绑定仓库。

| 操作 | 行为 |
|---|---|
| 刷新目录 | 更新条目与预览，之后可离线浏览缓存 |
| 检查更新 | 查询已下载主题默认分支的提交；不改原版，不直接使转换失效 |
| 下载／更新 | clone、fetch、快进更新；暂存完成后替换并备份旧目录，无版本变化时不替换 |
| 本地删除 | 移到 `backups/themes` 并记录原位置；不删除设备文件 |
| 刷新设备／上传 | 设备状态只表示存在；仅上传有效适配结果，按 C2 复制，不清除设备多余文件 |

原版有受跟踪修改、来源变化、本地版本变化或分叉时停止更新，不自动 hard reset。失败或取消保留正式内容；额外未跟踪文件随副本保留，冲突由 Git 拒绝。下载需临时副本和备份空间，使用现有清理入口管理。

下载和目录刷新实时读取 Git 输出；百分比属于当前接收、整理或写入阶段，不是批次总进度。未知进度显示动态等待，具体交互见 [页面约定](WINDOWS_UI_PLAN.md)。

## CLI

`catalog` 刷新目录；`list` 读取本地状态；`check-updates [ID…]` 检查已下载主题，省略 ID 时全部；`download／download-convert <ID…>` 下载更新；`convert／upload <ID…>` 转换或上传；`refresh` 刷新设备；`delete-original／delete-output <ID…>` 移除本地内容。原 sync 入口已移除，只有 refresh 和 upload 发现设备。

当前结论见 [状态](engine/STATUS.md)，详细测试过程见 [主题管理记录](TESTS_THEME_MANAGER_20261016.md)。
