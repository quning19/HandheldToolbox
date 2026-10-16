# 主题开发工具

这些脚本从旧 FrontendThemeConverter 迁入，保留逐主题构建与校验流程作为开发回归对照。正式 GUI/CLI 使用 src/theme_converter 的通用解析器。

从项目根目录运行：

```powershell
python tools/themes/build.py --batch batch1
python tools/themes/package.py --batch batch1
python tools/themes/validate.py --batch batch1
python tools/themes/verify.py --batch batch1
python tools/themes/badge.py --round <实验名>
```

路径通过 common.py 和 config/project.json 定义：输入为 test_data/themes，产物为 artifacts/themes，实验为 research/themes。这里的开发脚本不依赖相邻旧项目。上述校验命令仍需按本机约定单独获得测试批准，不因文档列出而自动执行。

extract_card_art.py 从四套完整主题提取各自实际提供的全部平台卡片缩略图，写入 frontend_gui 的随包资源及来源索引；与 ROM 扫描无关。来源许可随资源保留，原主题本身不进入软件包。
