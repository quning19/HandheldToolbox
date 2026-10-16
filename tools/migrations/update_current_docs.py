"""Keep pre-migration status as history and put the approved current structure first."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
for old, archived in (("docs/WINDOWS_GUI.md", "docs/archive/windows-gui-business-20261015.md"),
                      ("docs/engine/STATUS.md", "docs/engine/archive/status-20261015.md")):
    destination = ROOT / archived
    if not destination.exists():
        destination.write_bytes((ROOT / old).read_bytes())
for path in (ROOT / "docs/engine").glob("*.md"):
    text = path.read_text(encoding="utf-8").replace("](../src/", "](../../src/")
    text = text.replace("FrontendThemeConverter/source/configs/custom_systems-PG", "src/frontend_platforms/custom_systems-PG")
    text = text.replace("主题工具source/configs/custom_systems-PG", "本项目src/frontend_platforms/custom_systems-PG")
    text = text.replace("D:\\Game Tools\\HandheldTools\\FrontendThemeConverter\\source\\configs\\custom_systems-PG\\", "src/frontend_platforms/custom_systems-PG/")
    path.write_text(text, encoding="utf-8")
p = ROOT / "docs/WINDOWS_UI_PLAN.md"
t = p.read_text(encoding="utf-8")
t = t.replace("以下尚未实现，本轮仅记录，不执行转换、测试、构建、清理或资源导入。", "2026-10-16 用户已批准实施，当前代码见 [结构说明](ARCHITECTURE.md)、[主题解析](THEME_CONVERSION.md) 和 [工作目录](WORKSPACE_DATA.md)。下列为原验收清单；完成状态以本轮记录为准，旧测试记录不覆盖新实现。")
t = t.replace("当前实现仍为七套专用适配规则：", "迁移前基线为七套专用适配规则：")
t = t.replace("后续按第 6 项待办迁移为通用解析器", "本轮按第 6 项迁移为通用解析器")
p.write_text(t, encoding="utf-8")
p = ROOT / "src/AGENTS.md"
t = p.read_text(encoding="utf-8").replace("[STATUS.md](docs/STATUS.md)", "[状态](../docs/engine/STATUS.md)").replace("[README.md](README.md)", "[README](../README.md)").replace("(docs/archive/README.md)", "(../docs/archive/README.md)")
t = t.replace("本地命令入口为`python -m retrolibx.cli`。", "独立命令入口为 `python -m library_converter`、`python -m theme_converter`、`python -m frontend_gui`；原 `python -m retrolibx.cli` 保留。GUI 不拥有业务模型，两个 converter 互不导入、不依赖 Qt。")
p.write_text(t, encoding="utf-8")
p = ROOT / "pyproject.toml"
t = p.read_text(encoding="utf-8").replace('name = "retrolibx"', 'name = "frontend-trans-tool"', 1).replace('description = "Universal Retro Game Library Converter"', 'description = "Windows frontend toolkit with independent game-library and ES-DE theme converters"')
p.write_text(t, encoding="utf-8")
p = ROOT / "uv.lock"
t = p.read_text(encoding="utf-8").replace('name = "retrolibx"\nversion = "0.1.0"\nsource = { editable = "." }', 'name = "frontend-trans-tool"\nversion = "0.1.0"\nsource = { editable = "." }')
p.write_text(t, encoding="utf-8")
