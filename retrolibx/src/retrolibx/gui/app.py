"""Windows-native Fluent workspace; the first delivery is a business-free preview."""

import sys
import traceback

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QSizePolicy, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)
from qfluentwidgets import FluentIcon, Theme, setTheme, setThemeColor

from .library_page import LibraryPage
from .settings_page import SettingsPage
from .state import UiStore
from .themes_page import ThemesPage
from .widgets import caption


STYLE = """
QMainWindow { background: #f5f6f8; }
QWidget#sidebar { background: #eef0f4; border-right: 1px solid #e1e5ec; }
QWidget#libraryPage, QWidget#themesPage, QWidget#settingsPage { background: #f5f6f8; }
QLabel#pageTitle { font-size: 23px; font-weight: 600; color: #242a32; }
QLabel#brand { font-size: 16px; font-weight: 600; color: #242a32; }
QLabel#muted { color: #647083; }
QLabel#error { color: #ab3442; }
QLabel#previewBadge { color: #0968bb; background: #e7f0fa; padding: 7px; border-radius: 5px; }
QFrame#surface { background: white; border: 1px solid #e1e5ec; border-radius: 9px; }
QFrame#feedback { background: #edf4fc; border: 1px solid #d5e6f6; border-radius: 7px; }
QToolButton#nav { border: 0; border-left: 3px solid transparent; border-radius: 6px;
    background: transparent; text-align: left; padding: 12px 10px; color: #465160; }
QToolButton#nav:hover { background: #e4e8ee; }
QToolButton#nav:checked { background: white; border-left-color: #0968bb; color: #242a32; }
QToolButton#nav:focus { border: 1px solid #0968bb; }
QScrollArea { background: transparent; border: 0; }
QScrollArea > QWidget > QWidget { background: transparent; }
QStatusBar { background: white; border-top: 1px solid #e1e5ec; padding: 3px 8px; }
QStatusBar::item { border: none; }
"""


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
        sidebar.setFixedWidth(170)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(10, 22, 10, 12)
        nav.setSpacing(7)
        brand = QLabel("Frontend\nTrans Tool")
        brand.setObjectName("brand")
        nav.addWidget(brand)
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
            button = QToolButton()
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
        layout.addWidget(sidebar)
        layout.addWidget(self.pages, 1)
        self.statusBar().addWidget(caption("● 示例 GT78 · USB   |   内置存储 + SD 卡"), 1)
        self.statusBar().addPermanentWidget(caption("预览模式 · 不连接设备"))
        self.statusBar().setSizeGripEnabled(True)
        self.settings.workspace_changed.connect(self._workspace_changed)
        self.settings.definitions_changed.connect(self._definitions_changed)

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
    app.setFont(QFont("Segoe UI", 10))
    setTheme(Theme.LIGHT)
    setThemeColor("#0968bb")
    app.setStyleSheet(STYLE)

    def report_error(error_type, value, tb) -> None:
        traceback.print_exception(error_type, value, tb)
        QMessageBox.critical(None, "FrontendTransTool", f"界面操作失败：\n{value}")

    sys.excepthook = report_error
    try:
        store = UiStore()
    except (OSError, ValueError, TypeError, KeyError) as exc:
        QMessageBox.critical(None, "无法读取界面设置", str(exc) + "\n原配置已保留，请修正后重新打开。")
        return
    window = MainWindow(store)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
