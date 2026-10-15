"""Windows-native Fluent workspace; the first delivery is a business-free preview."""

import sys
import traceback

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)
from qfluentwidgets import FluentIcon

from .appearance import apply_appearance, colors, ui_font
from .library_page import LibraryPage
from .settings_page import SettingsPage
from .state import UiStore
from .themes_page import ThemesPage
from .widgets import NavigationButton, caption


class MainWindow(QMainWindow):
    def __init__(self, store: UiStore) -> None:
        super().__init__()
        self.setWindowTitle("FrontendTransTool · 界面预览")
        self.resize(1140, 750)
        self.setMinimumSize(1000, 650)
        self.store = store
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(184)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(12, 24, 12, 14)
        nav.setSpacing(8)
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        mark = QLabel("FT")
        mark.setObjectName("brandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(40, 40)
        brand_row.addWidget(mark)
        brand = QLabel("Frontend\nTrans Tool")
        brand.setObjectName("brand")
        brand_row.addWidget(brand, 1)
        nav.addLayout(brand_row)
        nav.addSpacing(3)
        badge = QLabel("界面预览 · 示例数据")
        badge.setObjectName("previewBadge")
        nav.addWidget(badge)
        nav.addSpacing(15)
        self.pages = QStackedWidget()
        self.pages.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.library = LibraryPage(store)
        self.themes = ThemesPage(store)
        self.settings = SettingsPage(store)
        self.navigation = QButtonGroup(self)
        self.navigation.setExclusive(True)
        entries = ((self.library, FluentIcon.GAME, "游戏库转换"), (self.themes, FluentIcon.BRUSH, "主题适配"), (self.settings, FluentIcon.SETTING, "设置"))
        for index, (page, icon, text) in enumerate(entries):
            self.pages.addWidget(page)
            if index == 2:
                nav.addStretch(1)
            button = NavigationButton()
            button.setObjectName("nav")
            button.setText(text)
            button.setIcon(icon.icon())
            button.setIconSize(QSize(19, 19))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setCheckable(True)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setAccessibleName(text)
            self.navigation.addButton(button, index)
            nav.addWidget(button)
            if index == 0:
                button.setChecked(True)
        nav.addWidget(caption("Windows 工作台"))
        self.navigation.idClicked.connect(self.pages.setCurrentIndex)
        self.navigation.idClicked.connect(lambda _index: self._refresh_icons())
        layout.addWidget(sidebar)
        layout.addWidget(self.pages, 1)
        device = QLabel("● 示例 GT78 · USB   |   内置存储 + SD 卡")
        device.setObjectName("deviceStatus")
        device.setFont(ui_font(12))
        self.statusBar().addWidget(device, 1)
        self.statusBar().addPermanentWidget(caption("预览模式 · 不连接设备"))
        self.statusBar().setSizeGripEnabled(True)
        self.settings.workspace_changed.connect(self._workspace_changed)
        self.settings.definitions_changed.connect(self._definitions_changed)
        self.settings.theme_changed.connect(self._apply_theme)
        self._refresh_icons()

    def _refresh_icons(self) -> None:
        c = colors(self.store.theme)
        for index, icon in enumerate((FluentIcon.GAME, FluentIcon.BRUSH, FluentIcon.SETTING)):
            button = self.navigation.button(index)
            button.setIcon(icon.icon(color=QColor(c["accent_ink"] if button.isChecked() else c["muted"])))

    def _apply_theme(self, mode: str) -> None:
        apply_appearance(QApplication.instance(), mode)
        self._refresh_icons()
        for card in self.library.grid.cards:
            card.update()

    def _workspace_changed(self) -> None:
        self.library.reset_workspace()
        self.themes.reset_workspace()

    def _definitions_changed(self) -> None:
        self.library.clear_source()
        self.themes.cancel_operation()
        for theme in self.themes.themes:
            theme.converted = False
        self.themes.update_paths()
        self.themes.render()
        self.themes.feedback.finish("平台定义已改变，请重新转换所需主题（示例）。")

    def closeEvent(self, event) -> None:
        self.library.shutdown()
        self.themes.cancel_operation()
        super().closeEvent(event)


def run() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("FrontendTransTool")
    # Fusion avoids Windows QStyle differences across newer Qt versions.
    app.setStyle("Fusion")

    def report_error(error_type, value, tb) -> None:
        traceback.print_exception(error_type, value, tb)
        QMessageBox.critical(None, "FrontendTransTool", f"界面操作失败：\n{value}")

    sys.excepthook = report_error
    try:
        store = UiStore()
    except (OSError, ValueError, TypeError, KeyError) as exc:
        apply_appearance(app, "light")
        QMessageBox.critical(None, "无法读取界面设置", str(exc) + "\n原配置已保留，请修正后重新打开。")
        return
    apply_appearance(app, store.theme)
    window = MainWindow(store)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
