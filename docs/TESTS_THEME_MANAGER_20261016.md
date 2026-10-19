# 官方主题管理定向测试

## 2026-10-19 用户手测反馈

用户已手动测试本轮主题管理，反馈“没有大问题”，本轮先整理收尾。以下“待用户验收”等表述描述测试当时状态，当前结论见 [状态](engine/STATUS.md)。

## 2026-10-16 自动测试记录

2026-10-16。用户批准执行新增的 16 项主题单元测试和 2 项 Qt 离屏测试，并允许遇到问题后针对性补测。

首批共 18 项，全部通过，pytest 报告耗时 4.69 秒。该批没有失败、跳过、修复或补测，没有扩大到全仓库回归。后续用户反馈的页面重排与性能定向测试见下文。

## 执行范围

- `tests/themes/test_catalog.py`：16 项。覆盖通用与 Android 列表合并、仓库冲突、预览路径边界、HTTPS 来源限制、更新查询与转换有效性分离、检查／下载失败保留旧内容、更新备份与过期、无变化不替换、删除原版后保留结果、旧导入不自动绑定、下架主题保留、默认分支解析、本地修改与分叉保护。Git 与网络均模拟，只处理隔离文件。
- `tests/gui/test_offscreen_workflows.py::test_offscreen_theme_filters_clear_hidden_batch_selection`：组合筛选、批量选择范围、筛选变化清空选择、空结果禁用操作、名称搜索。
- `tests/gui/test_offscreen_workflows.py::test_offscreen_theme_symbols_preserve_independent_states`：原版／适配／设备独立符号、需重转、未知设备、可访问说明及上传禁用。

使用项目既有 `retrolibx/.venv/Scripts/python.exe`（Python 3.12.14、pytest 9.1.1），`PYTHONPATH=src`，`QT_QPA_PLATFORM=offscreen`。项目要求 Python 3.12+，未使用机器笔记中的 Python 3.9。没有安装或变更运行环境。

执行命令（省略上述环境和隔离目录初始化）：

```powershell
& '.\retrolibx\.venv\Scripts\python.exe' -m pytest tests/themes/test_catalog.py tests/gui/test_offscreen_workflows.py::test_offscreen_theme_filters_clear_hidden_batch_selection tests/gui/test_offscreen_workflows.py::test_offscreen_theme_symbols_preserve_independent_states -v --tb=short -p no:cacheprovider
```

日志：[initial-tests.log](../test_data/theme-manager-tests-20261016-151654-ad40b10c/initial-tests.log)。GUI 隔离工作目录保存在同批次 `gui/` 中，未清理。

未下载真实官方目录或主题，未执行真实 Git 仓库下载更新，未连接或写入设备，未在桌面显示窗口，未运行 lint、类型检查、覆盖率或构建。本结果证明本次用例覆盖的逻辑与离屏交互通过，不代表实际网络、Windows 可见外观或 ES-DE 运行效果验收。

## 页面重排、操作范围与筛选性能

用户随后反馈页面布局、筛选等待和操作范围问题，确认按重排方案实施。沿用其“遇到问题可以单独补充测试”的授权，只执行相关 GUI 定向用例。

本轮 6 个不同用例均分别通过：原有组合筛选与符号状态两项，新增勾选范围、图片／行复用、布局／反馈区、导入后预览定位四项。没有运行无关 GUI 用例或重跑主题后端测试。

| 批次 | 范围与结果 | 日志 |
|---|---|---|
| 首轮 | 5 项通过，17.11 秒；71 行样本连续 24 次筛选共 0.0136 秒。截图检查发现离屏字体数据库为空，文字方框，不能据此验收视觉 | [redesign-tests.log](../test_data/theme-layout-tests-20261016-160341-2f21c798/redesign-tests.log) |
| 字体与预览调整后 | 勾选范围、图片复用、布局 3 项通过，11.18 秒；24 次筛选共 0.0041 秒，平均 0.17ms；没有重解码图片、请求缩略图或重建行 | [font-layout-recheck.log](../test_data/theme-layout-tests-20261016-160553-b2684ee9/font-layout-recheck.log) |
| 最终定位检查 | 布局与新增导入定位 2 项通过，4.26 秒；确认导入后清空旧筛选并显示新主题，仍需明确勾选才能操作；通过实际导航按钮生成最终截图 | [final-layout-import-tests.log](../test_data/theme-layout-tests-20261016-160735-3a354ed3/final-layout-import-tests.log) |

各批存在重复用例，不能相加为 10 个不同用例。性能计时为本地筛选处理函数，使用 71 行和三张生成的 1920×1080 图片，不包括首次加载、完整重绘或网络时间，不能当作所有机器的端到端响应保证。

布局测试只读 `workspace/themes/catalog` 的已有官方目录和截图，在隔离窗口显示，未读取或修改用户下载、转换结果。核对 1000×650、1140×750、1440×940 及亮暗两种外观；默认窗口列表有至少七行高度，无横向溢出，任务开始与结束不改变列表几何。Windows offscreen 启动时未加载系统字体，因此仅在测试夹具中注册已安装的微软雅黑、Segoe UI 和 Segoe UI Symbol，以获得可读证据；未修改产品字体或安装字体。

最终截图位于 `test_data/theme-layout-tests-20261016-160735-3a354ed3/gui/test_offscreen_theme_layout_and_compact_feedback/`：

- [默认尺寸深色](../test_data/theme-layout-tests-20261016-160735-3a354ed3/gui/test_offscreen_theme_layout_and_compact_feedback/themes-dark-1140.png)
- [最小尺寸深色](../test_data/theme-layout-tests-20261016-160735-3a354ed3/gui/test_offscreen_theme_layout_and_compact_feedback/themes-dark-1000.png)
- [大窗口浅色](../test_data/theme-layout-tests-20261016-160735-3a354ed3/gui/test_offscreen_theme_layout_and_compact_feedback/themes-light-1440.png)

没有联网下载、设备发现／写入、全仓库测试、lint、类型检查或构建。可读离屏截图已经静态检查，实际桌面 DPI、字体和操作感受仍由用户验收。

## 名称宽度、滚动条与预览缩略图

用户进一步要求缩短名称列、为纵向滚动条保留空间，并提供可直接点选的全部预览缩略图。仅执行这两项新用例及受影响的布局、筛选复用检查。沿用项目环境，增加 `QT_SCALE_FACTOR=1.25`，在 125% 缩放下核对：

- 名称列不超过 240 逻辑像素；滚动条独立占 20 逻辑像素，状态列与滚动条互不覆盖，1000／1140／1660 宽度下无横向溢出，能滚动至最后一行。
- 四张缩略图在最小面板同时可见；点击缩略图改变大图，箭头、页码和高亮保持同步；首尾循环不勾选主题；单图、无图和十图横向定位行为正确。
- 1000×650、1140×750、1440×940、亮暗两种外观，以及固定反馈区；截图选用已有官方四图主题 Alekfull NX，不下载或修改主题内容。
- 筛选仍复用原行和图像：71 行、24 次热筛选共 0.0038 秒，平均 0.16ms，仅处理函数时间。

首轮 4 项中 2 通过、2 失败，耗时 12.19 秒。一项测试直接比较滚动条父容器坐标与表格坐标，改为映射到表格后断言；另一项发现末张缩略图的 EnsureVisible 定位有 1 像素裁边，改为居中定位。检查截图另发现原生滚动条继承外观不清晰，增加独立轨道样式。

修正后只复测名称／滚动条、缩略图联动和受样式影响的布局 3 项，全部通过，9.76 秒；筛选复用在首轮已通过，没有重跑。这两轮覆盖 4 个不同用例，不能相加成 7 个独立用例。

- [首轮日志](../test_data/theme-gallery-tests-20261016-162529-8eeebafb/gallery-tests.log)
- [定向复测日志](../test_data/theme-gallery-tests-20261016-162652-bcefdf98/gallery-recheck.log)
- [默认尺寸深色截图](../test_data/theme-gallery-tests-20261016-162652-bcefdf98/gui/test_offscreen_theme_layout_and_compact_feedback/themes-dark-1140.png)
- [最小尺寸深色截图](../test_data/theme-gallery-tests-20261016-162652-bcefdf98/gui/test_offscreen_theme_layout_and_compact_feedback/themes-dark-1000.png)
- [大窗口浅色截图](../test_data/theme-gallery-tests-20261016-162652-bcefdf98/gui/test_offscreen_theme_layout_and_compact_feedback/themes-light-1440.png)

没有全量回归、联网下载、真实 Git 更新、设备连接／写入、lint、类型检查或构建。测试结果与截图不代替用户实际桌面验收。

## 下载与目录刷新实时进度

用户反馈勾选两个主题下载时列表变灰、无法看到进度，以及目录刷新进度停住后突然完成。源码定位到列表整体禁用及 Git 输出直到结束才返回；沿用“遇到问题可以单独补充测试”的授权，仅执行相关后端与 GUI 用例。

首轮共 27 项：原目录管理 16 项，新增批次／目录进度转发 2 项、本地进程输出 5 项，以及 Qt 交互 4 项（新增后台成功／取消 2 项，既有勾选范围和固定反馈布局 2 项）。26 项通过、1 项失败：取消后终止进程尚未完全退出。补充终止工具返回失败时的回退，并在 kill 后等待退出，该项单独复测通过。最后将进度绘制改为直接反映真实值，并明确模拟终止工具失败，只复查取消回退与后台成功／取消交互 3 项，全部通过。27 个不同用例均分别取得通过结果，没有最后全量重跑。

| 批次 | 结果 | 日志 |
|---|---|---|
| 首轮定向检查 | 26 通过、1 失败，17.91 秒 | [progress-tests.log](../test_data/theme-progress-tests-20261016-163848-9eab4cc7/progress-tests.log) |
| 取消问题修复后 | 1 通过，0.27 秒 | [cancel-recheck.log](../test_data/theme-progress-recheck-20261016-163948-b7673591/cancel-recheck.log) |
| 最后相关复查 | 3 通过，2.40 秒 | [final-progress.log](../test_data/theme-progress-final-20261016-164027-9699ee0b/final-progress.log) |

后端使用本地 Python 子进程模拟 Git 的 stderr 回车进度、静默连接和失败；确认 25% 及容量／速率在子进程仍运行时到达，未知进度保持 -1，静默时更新等待秒数，错误保留诊断，取消后进程结束。不下载真实仓库。

Qt 用真实 TaskHub／QThread，后台模拟两个主题的下载事件；确认动态等待条与确定百分比互换、绘制值立即更新、主线程定时器仍响应、列表可滚动和更换预览、勾选范围锁定，完成及取消后恢复操作。沿用 Python 3.12 项目环境、offscreen 和 125% 缩放，图片为生成样本。固定反馈布局检查覆盖三种尺寸及亮暗外观；最后的下载中截图见各参数化用例目录下 `live-download.png`。

未操作用户已运行的 GUI 或 Git 下载进程，未联网下载、连接／写入设备、运行全仓库测试、lint、类型检查或构建；实际网络下的传输显示仍需用户重新打开工具后验收。

## 缩略图等比缩放与尺寸上限

根据用户要求，将预览缩略图区域从宽度动态、高度固定改为宽高联动，16:9 图片框最大约 150×84 逻辑像素；不同原图比例保持完整显示。预览使用独立的较大解码缓存，列表继续使用小图缓存。

沿用既有定向测试授权，只执行新增响应尺寸／比例用例，以及受影响的缩略图联动、固定反馈布局和筛选图像复用用例，共 4 项，全部通过，10.90 秒，无失败或复测。Python 3.12 项目环境、offscreen、125% 缩放，仅使用生成图片和隔离工作目录，未联网或操作设备。

新增用例核对 1000／1440／2000 窗口宽度下宽高同时增减，最大图片框达到 150×84，四张缩略图始终完整可见，16:9、4:3 和竖图没有拉伸。既有布局用例继续核对三种尺寸和亮暗外观，筛选复用用例确认窗口／筛选操作不重复解码。

- [日志](../test_data/theme-thumbnail-scale-20261016-164411-1055b5cc/thumbnail-scale.log)
- [宽窗口比例截图](../test_data/theme-thumbnail-scale-20261016-164411-1055b5cc/gui/test_offscreen_theme_thumbnails_scale_together_without_stretching/thumbnail-scale-2000.png)
- [窄窗口比例截图](../test_data/theme-thumbnail-scale-20261016-164411-1055b5cc/gui/test_offscreen_theme_thumbnails_scale_together_without_stretching/thumbnail-scale-1000.png)

## 放大带框状态图标

用户要求状态符号更大、具有类似 checkbox 的方框。实现为 28×28 逻辑像素圆角框、22px 符号、状态色边框与浅底，由表格代理绘制，保留状态说明和独立批量勾选。

沿用此前定向测试授权，执行新增被动状态图标交互用例，以及既有独立状态语义、布局／固定反馈、筛选图像复用，共 4 项。首轮 3 通过、1 失败，10.05 秒：Qt 默认 item flags 包含可勾选标志，尽管状态项没有 CheckStateRole。将状态项明确设置为仅可选择和启用后，该项单独复测通过，1.96 秒。4 个不同用例均分别取得通过结果，没有全量重跑。复测有 2 条来自 QFluentWidgets 的 QMouseEvent.pos 弃用警告，不影响结果。

125% offscreen 下核对亮暗截图、三列完整说明、无逐格控件、图标不参与勾选，点击需重转图标只切换预览，下载按钮仍因未勾选而禁用。布局和筛选复用用例首轮已通过，未重复执行。未联网、连接设备、运行全仓库测试或构建。

- [首轮日志](../test_data/theme-status-icons-20261016-165147-9f50dc03/status-icons.log)
- [单项复测日志](../test_data/theme-status-icons-recheck-20261016-165213-d97fc582/status-icons-recheck.log)
- [深色图标截图](../test_data/theme-status-icons-recheck-20261016-165213-d97fc582/gui/test_offscreen_theme_framed_status_icons_are_passive/framed-status-dark.png)
- [浅色图标截图](../test_data/theme-status-icons-recheck-20261016-165213-d97fc582/gui/test_offscreen_theme_framed_status_icons_are_passive/framed-status-light.png)

用户随后补充：没有的状态保留原符号，以便与带框状态区分。×、— 已恢复为原来的 18px 无框绘制，其余状态保持 28px 框和放大符号。只复查既有被动图标交互用例，1 项通过、1.94 秒，并核对亮暗截图中的外观区分；未新增用例或扩大测试，仍有相同的 2 条上游弃用警告。[日志](../test_data/theme-status-contrast-20261016-165536-0272d53e/status-contrast.log)，[深色效果](../test_data/theme-status-contrast-20261016-165536-0272d53e/gui/test_offscreen_theme_framed_status_icons_are_passive/framed-status-dark.png)。
