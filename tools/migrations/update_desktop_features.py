"""Apply GUI integration edits for the approved business-package migration."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
p = ROOT / "src/frontend_gui/widgets.py"
t = p.read_text(encoding="utf-8")
t = t.replace('from .appearance import DARK, LIGHT, colors, ui_font', 'from .appearance import DARK, LIGHT, colors, ui_font\nfrom .card_art import resolve_art')
t = t.replace('def __init__(self, item: PlatformInfo, parent: QWidget)', 'def __init__(self, item: PlatformInfo, parent: QWidget, style="canvas")')
t = t.replace('self.art = QPixmap(str(Path(__file__).parent / "assets/platforms" / (item.art + ".webp")))', 'self.set_style(style)')
needle = '    def update_details(self) -> None:'
t = t.replace(needle, '    def set_style(self, style):\n        path = resolve_art(style, self.item.art, self.item.parent_art)\n        self.art = QPixmap(str(path)) if path else QPixmap()\n        self.update()\n\n' + needle)
t = t.replace('self.cards: list[PlatformCard] = []', 'self.cards: list[PlatformCard] = []\n        self.style = "canvas"')
t = t.replace('card = PlatformCard(item, self)', 'card = PlatformCard(item, self, self.style)')
t = t.replace('    def selected(self) -> list[PlatformInfo]:', '    def set_style(self, style):\n        self.style = style\n        for card in self.cards:\n            card.set_style(style)\n\n    def selected(self) -> list[PlatformInfo]:')
p.write_text(t, encoding="utf-8")
p = ROOT / "src/frontend_gui/library_page.py"
t = p.read_text(encoding="utf-8").replace('self.grid = PlatformGrid()', 'self.grid = PlatformGrid()\n        self.grid.set_style(store.card_style)')
p.write_text(t, encoding="utf-8")
p = ROOT / "src/frontend_gui/settings_page.py"
t = p.read_text(encoding="utf-8")
t = t.replace('from .appearance import DARK, LIGHT', 'from .appearance import DARK, LIGHT\nfrom frontend_common.state import CARD_STYLES\nfrom .cleanup_dialog import CleanupDialog')
t = t.replace('    theme_changed = Signal(str)', '    theme_changed = Signal(str)\n    card_style_changed = Signal(str)\n    workspace_cleaned = Signal()')
t = t.replace('def __init__(self, store: UiStore) -> None:\n        super().__init__()\n        self.store = store\n        self.setObjectName("settingsPage")', 'def __init__(self, store: UiStore, hub) -> None:\n        super().__init__()\n        self.store, self.hub = store, hub\n        self.setObjectName("settingsPage")')
t = t.replace('        content.addWidget(appearance)', '''        art_row = QHBoxLayout()
        art_row.addWidget(caption("平台卡片风格"), 1)
        self.card_style = ComboBox()
        for key, title in CARD_STYLES.items():
            self.card_style.addItem(title, userData=key)
        self.card_style.setCurrentIndex(list(CARD_STYLES).index(store.card_style))
        self.card_style.currentIndexChanged.connect(self._change_card_style)
        art_row.addWidget(self.card_style)
        appearance_layout.addLayout(art_row)
        content.addWidget(appearance)''')
t = t.replace('        self.feedback = caption("")', '''        clean_frame, clean_controls = panel()
        clean_row = QHBoxLayout()
        clean_row.addWidget(heading("工作目录清理", "预览并手动清理临时文件、备份与恢复资料、历史日志", section=True), 1)
        clean_button = PushButton("清理工作目录…")
        clean_button.clicked.connect(self._cleanup)
        clean_row.addWidget(clean_button)
        clean_controls.addLayout(clean_row)
        content.addWidget(clean_frame)
        self.feedback = caption("\\n".join(store.catalog_notices))''')
t = t.replace('    def _change_theme(self, checked: bool)', '''    def _cleanup(self):
        dialog = CleanupDialog(self.store, self.hub, self)
        dialog.exec()
        if dialog.did_clean:
            self.workspace_cleaned.emit()

    def _change_card_style(self, _index):
        try:
            self.store.save_card_style(self.card_style.currentData())
        except (OSError, ValueError) as exc:
            self.card_style.blockSignals(True)
            self.card_style.setCurrentIndex(list(CARD_STYLES).index(self.store.card_style))
            self.card_style.blockSignals(False)
            self.feedback.setText("卡片风格保存失败：" + str(exc))
            return
        self.card_style_changed.emit(self.store.card_style)

    def _change_theme(self, checked: bool)''')
p.write_text(t, encoding="utf-8")
p = ROOT / "src/frontend_gui/app.py"
t = p.read_text(encoding="utf-8").replace('SettingsPage(store)', 'SettingsPage(store, self.tasks)')
t = t.replace('        self.settings.theme_changed.connect(self._apply_theme)', '        self.settings.theme_changed.connect(self._apply_theme)\n        self.settings.card_style_changed.connect(self.library.grid.set_style)\n        self.settings.workspace_cleaned.connect(self.library.clear_source)')
t = t.replace('平台定义已改变，请重新加载游戏库，并重新转换所需主题。', '平台定义已更新；受影响主题显示需要重新转换，请重新加载游戏库。')
p.write_text(t, encoding="utf-8")
