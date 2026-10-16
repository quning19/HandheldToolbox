"""The two desktop palettes and shared, DPI-aware text styles."""

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, isDarkTheme, setFontFamilies, setTheme, setThemeColor


FONT_FAMILIES = ["Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI Variable", "Segoe UI"]

LIGHT = {
    "canvas": "#F2F5FB", "surface": "#FFFFFF", "raised": "#F8FAFF",
    "sidebar": "#E7EEF8", "border": "#D9E2F0", "hover": "#EDF1FC",
    "ink": "#1F2A44", "muted": "#60718A", "disabled": "#8491A8",
    "accent": "#4F63D8", "accent_soft": "#E9EDFF", "accent_ink": "#4254BD",
    "success": "#008B7A", "success_soft": "#E3F5EF",
    "warning": "#946000", "warning_soft": "#FFF3DA",
    "danger": "#B53E58", "danger_soft": "#FCEBF0",
}
DARK = {
    "canvas": "#111827", "surface": "#1B2437", "raised": "#222E44",
    "sidebar": "#151E30", "border": "#34415B", "hover": "#29354D",
    "ink": "#E8EDF8", "muted": "#A5B2C9", "disabled": "#75849E",
    "accent": "#9AA8FF", "accent_soft": "#2C3658", "accent_ink": "#B4BEFF",
    "success": "#63D5C4", "success_soft": "#193D3D",
    "warning": "#EDC57B", "warning_soft": "#433A28",
    "danger": "#F099AB", "danger_soft": "#472D3F",
}


def colors(mode: str | None = None) -> dict[str, str]:
    return DARK if mode == "dark" or (mode is None and isDarkTheme()) else LIGHT


def ui_font(size: int = 14, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPixelSize(size)
    font.setWeight(weight)
    return font


def stylesheet(c: dict[str, str]) -> str:
    return f"""
    QMainWindow, QDialog {{ background: {c['canvas']}; color: {c['ink']}; }}
    QLabel {{ color: {c['ink']}; }}
    QWidget#sidebar {{ background: {c['sidebar']}; border-right: 1px solid {c['border']}; }}
    QWidget#libraryPage, QWidget#themesPage, QWidget#settingsPage {{ background: {c['canvas']}; }}
    QLabel#pageTitle {{ font-size: 24px; font-weight: 600; color: {c['ink']}; }}
    QLabel#sectionTitle {{ font-size: 17px; font-weight: 600; color: {c['ink']}; }}
    QDialog QLabel#pageTitle {{ font-size: 21px; }}
    QLabel#brand {{ font-size: 16px; font-weight: 600; color: {c['ink']}; }}
    QLabel#brandMark {{ background: transparent; }}
    QLabel#muted {{ color: {c['muted']}; }}
    QLabel#error {{ color: {c['danger']}; }}
    QLabel#previewBadge {{ color: {c['accent_ink']}; background: {c['accent_soft']};
        padding: 6px 9px; border-radius: 6px; font-size: 12px; }}
    QLabel#deviceStatus {{ color: {c['success']}; }}
    QLabel#statusBadge {{ padding: 4px 9px; border-radius: 5px; font-size: 12px; font-weight: 500; }}
    QLabel#statusBadge[tone="success"] {{ color: {c['success']}; background: {c['success_soft']}; }}
    QLabel#statusBadge[tone="warning"] {{ color: {c['warning']}; background: {c['warning_soft']}; }}
    QLabel#statusBadge[tone="accent"] {{ color: {c['accent_ink']}; background: {c['accent_soft']}; }}
    QLabel#statusBadge[tone="muted"] {{ color: {c['muted']}; background: {c['raised']}; }}
    QFrame#surface {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px; }}
    QFrame#feedback {{ background: {c['accent_soft']}; border: 1px solid {c['border']}; border-radius: 8px; }}
    QToolButton#nav {{ border: 1px solid transparent; border-left: 3px solid transparent; border-radius: 7px;
        background: transparent; text-align: left; padding: 12px 11px; color: {c['muted']}; }}
    QToolButton#nav:hover {{ background: {c['hover']}; }}
    QToolButton#nav:checked {{ background: {c['accent_soft']}; border-left-color: {c['accent']}; color: {c['accent_ink']}; }}
    QToolButton#nav[keyboardFocus="true"] {{ border-color: {c['accent']}; }}
    QScrollArea {{ background: transparent; border: 0; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QTableView {{ background: {c['surface']}; color: {c['ink']};
        border: 1px solid {c['border']}; border-radius: 8px; gridline-color: {c['border']}; }}
    QHeaderView::section {{ background: {c['raised']}; color: {c['muted']};
        padding: 10px 12px; border: 0; border-bottom: 1px solid {c['border']}; font-size: 13px; }}
    QStatusBar {{ background: {c['surface']}; color: {c['muted']};
        border-top: 1px solid {c['border']}; padding: 4px 10px; }}
    QStatusBar::item {{ border: none; }}
    QToolTip {{ color: {c['ink']}; background: {c['raised']}; border: 1px solid {c['border']}; padding: 6px; }}
    """


def apply_appearance(app: QApplication, mode: str) -> None:
    c = colors(mode)
    setFontFamilies(FONT_FAMILIES, save=False)
    app.setFont(ui_font())
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: "canvas", QPalette.ColorRole.WindowText: "ink",
        QPalette.ColorRole.Base: "surface", QPalette.ColorRole.AlternateBase: "raised",
        QPalette.ColorRole.Text: "ink", QPalette.ColorRole.Button: "surface",
        QPalette.ColorRole.ButtonText: "ink", QPalette.ColorRole.PlaceholderText: "muted",
        QPalette.ColorRole.Highlight: "accent", QPalette.ColorRole.Link: "accent",
        QPalette.ColorRole.ToolTipBase: "raised", QPalette.ColorRole.ToolTipText: "ink",
    }
    for role, token in roles.items():
        palette.setColor(role, QColor(c[token]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(DARK["canvas"] if mode == "dark" else "#FFFFFF"))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(c["disabled"]))
    app.setPalette(palette)
    setTheme(Theme.DARK if mode == "dark" else Theme.LIGHT, save=False)
    setThemeColor(c["accent"], save=False)
    app.setStyleSheet(stylesheet(c))
