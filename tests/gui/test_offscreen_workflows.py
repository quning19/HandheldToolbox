"""Qt offscreen only: never creates a desktop window or connects a device."""
from pathlib import Path
import os
from unittest.mock import patch

import pytest

from tests.themes.test_full_exports import session_directory


@pytest.fixture(scope="module")
def qt_app():
    assert os.environ.get("QT_QPA_PLATFORM") == "offscreen", "此测试只允许 offscreen 平台"
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    yield app


@pytest.fixture
def window(qt_app, request):
    from frontend_common.state import UiStore
    from frontend_gui.appearance import apply_appearance
    from frontend_gui.app import MainWindow
    application = session_directory() / "gui" / request.node.name
    application.mkdir(parents=True)
    with patch("frontend_common.state.app_directory", return_value=application):
        store = UiStore()
        store.change_workspace(application / "w")
        apply_appearance(qt_app, store.theme)
        main = MainWindow(store)
        main.show()  # QT_QPA_PLATFORM=offscreen; nothing appears on the user's desktop.
        qt_app.processEvents()
        yield main
        assert not main.tasks.busy
        main.close()
        main.deleteLater()
        qt_app.processEvents()


def test_offscreen_startup_pages_and_fixed_progress(window, qt_app):
    size = window.size()
    for index, page in enumerate((window.library, window.themes, window.settings)):
        window.pages.setCurrentIndex(index)
        qt_app.processEvents()
        assert window.size() == size
        if index < 2:
            content = page.scroll if index == 0 else page.table
            before = content.geometry()
            page.feedback.update_progress("测试进度", 50, False)
            qt_app.processEvents()
            assert content.geometry() == before, "进度条挤动其他控件"
            page.feedback.finish("完成")
            qt_app.processEvents()
            assert content.geometry() == before
        assert window.grab().save(str(window.store.settings_file.parent / f"page-{index}.png"))
    window.resize(1280, 800)
    qt_app.processEvents()
    assert window.width() == 1280 and window.height() == 800


def test_offscreen_color_modes_and_four_card_styles(window, qt_app):
    from library_converter.desktop import PlatformInfo
    from frontend_common.state import UiStore, CARD_STYLES
    window.library.grid.append(PlatformInfo("GBA", "GBA", "gba", 8, 8, 0))
    for index, style in enumerate(CARD_STYLES):
        window.settings.card_style.setCurrentIndex(index)
        qt_app.processEvents()
        assert window.store.card_style == style
        assert not window.library.grid.cards[0].art.isNull(), style
    for dark in (True, False):
        window.settings.theme_switch.setChecked(dark)
        qt_app.processEvents()
        assert window.store.theme == ("dark" if dark else "light")
        assert window.grab().save(str(window.store.settings_file.parent / ("dark.png" if dark else "light.png")))
    with patch("frontend_common.state.app_directory", return_value=window.store.settings_file.parent):
        reopened = UiStore()
    assert reopened.card_style == "iisu" and reopened.theme == "light"


def test_offscreen_platform_management_and_empty_theme_list(window, qt_app):
    from frontend_platforms.user_catalog import PlatformDefinition
    assert window.themes.themes == []
    extra = PlatformDefinition("gba-functional", "GBA 测试分类", "GBA 测试分类", "gba", "separate", "TEST")
    window.store.save_definitions([*window.store.definitions, extra])
    window.settings.platforms.render()
    window.settings.platforms.search.setText(extra.name)
    qt_app.processEvents()
    assert window.settings.platforms.table.rowCount() == 1
    assert window.settings.platforms.table.item(0, 0).text() == extra.name
    window.settings.platforms.delete(extra)
    qt_app.processEvents()
    assert extra.id not in {item.id for item in window.store.definitions}
    assert window.settings.platforms.table.rowCount() == 0
