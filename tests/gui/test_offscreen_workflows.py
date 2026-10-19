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
    from PySide6.QtGui import QFontDatabase
    app = QApplication.instance() or QApplication([])
    if os.name == "nt" and not QFontDatabase.families():
        # Windows offscreen can start without the native font database. Register
        # installed fonts for readable test evidence; product font settings stay unchanged.
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("msyh.ttc", "segoeui.ttf", "seguisym.ttf"):
            if (fonts / name).is_file():
                assert QFontDatabase.addApplicationFont(str(fonts / name)) >= 0
    assert QFontDatabase.families(), "离屏截图必须具有可读字体"
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


def test_savedeck_target_switch_resets_session_and_keeps_the_source(window, qt_app):
    page = window.library
    page.source.setCurrentIndex(1)
    page.computer_root.setText(str(window.store.workspace.parent / "roms"))
    source = page.source_key()
    page.session = object()
    page.shared.setChecked(True)
    page.frontend.setCurrentText("SaveDeck")
    qt_app.processEvents()
    assert page.session is None
    assert page.source_key() == source
    assert page.shared.isHidden() and not page.shared.isChecked()
    assert page.full.text() == "全量覆盖"
    assert page.start.text() == "导出到原目录"
    page.source.setCurrentIndex(0)
    assert page.start.text() == "导出并推送"
    page.frontend.setCurrentText("ES-DE")
    assert not page.shared.isHidden()
    assert page.start.text() == "开始转换"


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


def test_offscreen_theme_filters_clear_hidden_batch_selection(window, qt_app):
    from theme_converter.service import ThemeInfo
    page = window.themes
    page.themes = [ThemeInfo("a", "Canvas", original=True, repository="https://example.org/a.git",
                             converted=True, device=True, update_available=True),
                   ThemeInfo("b", "Modern", device=False)]
    page.render()
    assert page.table.columnCount() == 6
    page.select_all(True)
    assert page.selected == {"a", "b"}
    page.original_filter.setCurrentIndex(3)
    assert len(page.visible_themes()) == 1
    assert page.table.rowCount() == 2
    assert page.table.isRowHidden(1)
    assert page.selected == set()
    assert page.table.item(0, 2).text() == "Canvas"
    page.select_all(True)
    assert page.selected == {"a"}
    page.device_filter.setCurrentIndex(2)
    assert not page.visible_themes()
    assert all(page.table.isRowHidden(row) for row in range(page.table.rowCount()))
    assert not page.upload.isEnabled()
    page.reset_filters()
    assert page.table.rowCount() == 2
    page.search.setText("modern")
    assert len(page.visible_themes()) == 1
    assert page.table.isRowHidden(0) and not page.table.isRowHidden(1)
    assert page.current_id == "b"


def test_offscreen_theme_symbols_preserve_independent_states(window, qt_app):
    from PySide6.QtCore import Qt
    from frontend_gui.themes_page import theme_symbols
    from theme_converter.service import ThemeInfo
    info = ThemeInfo("a", "Canvas", original=True, converted=True, device=True, update_available=True)
    assert [state[0] for state in theme_symbols(info)] == ["↑", "✓", "✓"]
    info.converted, info.stale, info.device = False, True, None
    assert [state[0] for state in theme_symbols(info)] == ["↑", "↻", "—"]
    page = window.themes
    page.themes = [info]
    page.render()
    assert page.table.item(0, 4).data(Qt.ItemDataRole.AccessibleTextRole).startswith("需要重新转换")
    assert page.table.item(0, 4).text() == "↻"
    assert page.table.cellWidget(0, 4) is None
    assert not page.upload.isEnabled()


def test_offscreen_theme_framed_status_icons_are_passive(window, qt_app):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from frontend_gui.appearance import apply_appearance
    from theme_converter.service import ThemeInfo
    page = window.themes
    page.themes = [
        ThemeInfo("done", "已完成", original=True, converted=True, device=True),
        ThemeInfo("update", "有更新、需重转", original=True, update_available=True, stale=True, device=False),
        ThemeInfo("unknown", "尚未获取"),
        ThemeInfo("error", "检查／适配失败", original=True, update_error="offline", reason="适配失败"),
    ]
    page.render()
    window.navigation.button(1).click()
    window.resize(1140, 750)
    for mode in ("dark", "light"):
        apply_appearance(qt_app, mode)
        qt_app.processEvents()
        assert page.table.horizontalScrollBar().maximum() == 0
        for row in range(4):
            for column in (3, 4, 5):
                item = page.table.item(row, column)
                assert item.data(Qt.ItemDataRole.CheckStateRole) is None
                assert not item.flags() & Qt.ItemFlag.ItemIsUserCheckable
                assert item.toolTip() and item.data(Qt.ItemDataRole.AccessibleTextRole)
                assert page.table.cellWidget(row, column) is None
        QTest.mouseClick(page.table.viewport(), Qt.MouseButton.LeftButton,
                         pos=page.table.visualItemRect(page.table.item(1, 4)).center())
        assert page.current_id == "update" and not page.selected
        assert page.table.item(1, 4).text() == "↻"
        assert not page.download.isEnabled()
        assert window.grab().save(str(window.store.settings_file.parent / f"framed-status-{mode}.png"))


def theme_examples(window):
    """Seventy-one themes with real-size generated artwork, isolated from user data."""
    from PySide6.QtGui import QColor, QImage
    from theme_converter.service import ThemeInfo
    image_directory = window.store.settings_file.parent / "images"
    image_directory.mkdir()
    paths = []
    for index, color in enumerate(("#3b648b", "#856951", "#44775f")):
        image = QImage(1920, 1080, QImage.Format.Format_RGB32)
        image.fill(QColor(color))
        path = image_directory / f"preview-{index}.jpg"
        assert image.save(str(path))
        paths.append(path)
    return [ThemeInfo(str(index), f"Theme {index:02d}", original=index % 2 == 0,
                      converted=index % 3 == 0, device=index % 2 == 0,
                      repository=f"https://example.org/theme-{index}.git",
                      update_available=index % 4 == 0, author="Example author",
                      variants=["List", "Grid"], color_schemes=["Light", "Dark"],
                      aspect_ratios=["16:9", "4:3"], screenshots=[(paths[index % 3], "System view"),
                                                               (paths[(index + 1) % 3], "Gamelist view")])
            for index in range(71)]


def test_offscreen_theme_actions_only_target_checkboxes(window, qt_app):
    from types import SimpleNamespace
    from PySide6.QtCore import Qt
    page = window.themes
    page.themes = theme_examples(window)[:2]
    page.render()
    assert page.current_id == "0" and page.action_themes() == []
    assert not page.download.isEnabled() and not page.convert.isEnabled()
    with patch.object(page.hub, "start", return_value=False) as start:
        page.begin("download")
        start.assert_not_called()
        page.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
        page.table.setCurrentCell(1, 2)
        assert page.current_id == "1"
        assert page.selected == {"0"}
        assert page.download.isEnabled() and page.convert.isEnabled()
        page.begin("download")
        worker = SimpleNamespace(isInterruptionRequested=lambda: False, progress=SimpleNamespace(emit=lambda *_: None))
        with patch("frontend_gui.themes_page.run_themes") as run:
            start.call_args.args[0](worker)
            assert run.call_args.args[3] == ["0"]
        page.table.item(1, 0).setCheckState(Qt.CheckState.Checked)
        assert not page.convert.isEnabled(), "混选未下载主题时应解释并禁用转换"
        assert "先下载" in page.convert.toolTip()
        page.begin("download")
        with patch("frontend_gui.themes_page.run_themes") as run:
            start.call_args.args[0](worker)
            assert run.call_args.args[3] == ["0", "1"]
        page.select_all(False)
        assert not page.download.isEnabled() and page.action_themes() == []
    assert page.import_button in page.page_more.menu().actions()
    assert page.download_convert in page.more.menu().actions()


@pytest.mark.parametrize("cancel", [False, True])
def test_offscreen_theme_live_download_feedback_and_browsing(window, qt_app, cancel):
    """A real QThread with a controlled fake transfer; no network or device."""
    import queue
    import time
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtTest import QTest
    from frontend_common.jobs import checkpoint
    page = window.themes
    page.themes = theme_examples(window)
    page.render()
    window.navigation.button(1).click()
    for row in (0, 1):
        page.table.item(row, 0).setCheckState(Qt.CheckState.Checked)
    commands = queue.Queue()
    heartbeat = []
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: heartbeat.append(True))
    timer.start()
    def transfer(_operation, _workspace, _definitions, identities, _device, cancelled, progress):
        assert identities == ["0", "1"]
        progress("[1/2] Theme 00 · 等待服务器响应…", -1, True)
        while True:
            checkpoint(cancelled)
            try:
                command = commands.get(timeout=0.02)
            except queue.Empty:
                continue
            if command == "done":
                return {"themes": page.themes, "message": "2 个主题下载完成"}
            progress(*command)
    def wait_until(condition):
        deadline = time.monotonic() + 4
        while not condition() and time.monotonic() < deadline:
            qt_app.processEvents()
            QTest.qWait(10)
        assert condition(), "未及时收到后台线程进度／完成信号"
    with patch("frontend_gui.themes_page.run_themes", side_effect=transfer), \
            patch("frontend_gui.themes_page.managed_themes", return_value=page.themes):
        try:
            page.begin("download")
            wait_until(lambda: "等待服务器" in page.feedback.message.toolTip())
            assert page.hub.busy and page.table.isEnabled()
            assert page.feedback.wait_bar.isStarted() and page.feedback.wait_bar.isVisible()
            assert not page.feedback.bar.isVisible()
            assert not page.download.isEnabled() and not page.select_visible.isEnabled()
            assert not page.table.item(0, 0).flags() & Qt.ItemFlag.ItemIsUserCheckable
            # User can browse another theme and scroll without changing this batch.
            page.table.setCurrentCell(30, 2)
            page.table.scrollToItem(page.table.item(30, 2))
            assert page.current_id == "30" and page.selected == {"0", "1"}
            assert page.table.verticalScrollBar().value() > 0
            commands.put(("[1/2] Theme 00 · 接收数据: 25%, 2.00 MiB | 1.00 MiB/s", 25, True))
            wait_until(lambda: page.feedback.percent.text() == "25%")
            assert page.feedback.bar.isVisible() and page.feedback.bar.value() == 25
            assert page.feedback.bar.getVal() == 25, "绘制进度应直接反映真实百分比"
            assert not page.feedback.wait_bar.isStarted()
            assert "MiB/s" in page.feedback.message.toolTip()
            assert heartbeat, "Qt 主线程必须持续处理事件"
            assert window.grab().save(str(window.store.settings_file.parent / "live-download.png"))
            if cancel:
                page.feedback.stop.click()
            else:
                commands.put(("[2/2] Theme 01 · 整理数据: 80%", 80, True))
                wait_until(lambda: page.feedback.percent.text() == "80%")
                commands.put("done")
            wait_until(lambda: not page.hub.busy)
            assert page.table.item(0, 0).flags() & Qt.ItemFlag.ItemIsUserCheckable
            assert page.download.isEnabled()
            assert not page.feedback.bar.isVisible() and not page.feedback.wait_bar.isStarted()
            assert ("取消" if cancel else "2 个主题下载完成") in page.feedback.message.toolTip()
        finally:
            commands.put("done")
            if page.hub.busy:
                page.hub.cancel()
                page.hub.worker.wait(4000)
                qt_app.processEvents()
            timer.stop()


def test_offscreen_theme_filters_reuse_rows_and_decoded_images(window, qt_app):
    import time
    from frontend_gui import themes_page
    page = window.themes
    page.themes = theme_examples(window)
    with patch.object(themes_page, "scaled_image", wraps=themes_page.scaled_image) as decode:
        page.render()
        assert decode.call_count == 6, "三张列表缩略图、两张较大预览缩略图及当前大图"
    row_items = [page.table.item(row, 2) for row in range(71)]
    with patch.object(themes_page, "scaled_image", wraps=themes_page.scaled_image) as decode, \
            patch.object(page, "thumbnail", wraps=page.thumbnail) as thumbnail:
        started = time.perf_counter()
        for _index in range(6):
            page.original_filter.setCurrentIndex(2)
            page.original_filter.setCurrentIndex(0)
            page.search.setText("Theme 0")
            page.search.clear()
        elapsed = time.perf_counter() - started
        decode.assert_not_called()
        thumbnail.assert_not_called()
    assert all(page.table.item(row, 2) is row_items[row] for row in range(71))
    assert all(page.table.cellWidget(row, column) is None for row in range(71) for column in range(6))
    print(f"FILTER_PERFORMANCE: 71 rows, 24 filter changes, {elapsed:.4f}s total, {elapsed / 24 * 1000:.2f}ms/change")
    assert elapsed < 2.4, "24 次本地筛选不应平均超过 100ms"


def test_offscreen_theme_layout_and_compact_feedback(window, qt_app):
    from frontend_gui.appearance import apply_appearance
    from theme_converter.catalog import read_catalog
    from theme_converter.service import ThemeInfo
    page = window.themes
    cache = os.environ.get("FTT_THEME_PREVIEW_CATALOG")
    if cache:
        page.themes = [ThemeInfo("official-" + entry["reponame"], entry["name"], author=entry.get("author", ""),
                                 repository=entry["url"], screenshots=entry["previews"],
                                 aspect_ratios=entry.get("aspectRatios", []), variants=entry.get("variants", []),
                                 color_schemes=entry.get("colorSchemes", [])) for entry in read_catalog(Path(cache))]
    else:
        page.themes = theme_examples(window)
    page.render()
    window.navigation.button(1).click()
    four_previews = next((row for row, theme in enumerate(page.themes) if len(theme.screenshots) == 4), 0)
    page.table.setCurrentCell(four_previews, 2)
    for mode in ("dark", "light"):
        apply_appearance(qt_app, mode)
        for width, height in ((1000, 650), (1140, 750), (1440, 940)):
            window.resize(width, height)
            qt_app.processEvents()
            assert window.width() == width and window.height() == height, "主题页不能撑大窗口"
            assert page.table.horizontalScrollBar().maximum() == 0
            assert page.feedback.height() == 32
            before = page.table.geometry()
            page.feedback.update_progress("正在处理勾选的 3 个主题…", 45, True)
            qt_app.processEvents()
            assert page.table.geometry() == before
            page.feedback.finish("处理完成")
            qt_app.processEvents()
            assert page.table.geometry() == before
            if width == 1140:
                assert page.table.viewport().height() >= 448, "默认尺寸至少提供七行主题的高度"
            assert window.grab().save(str(window.store.settings_file.parent / f"themes-{mode}-{width}.png"))


def test_offscreen_theme_import_result_clears_filters_without_batch_selection(window, qt_app):
    from theme_converter.service import ThemeInfo
    page = window.themes
    page.themes = [ThemeInfo("a", "Canvas")]
    page.render()
    page.search.setText("Canvas")
    imported = ThemeInfo("local", "Local theme", original=True)
    page.completed({"themes": [*page.themes, imported], "identity": imported.id, "message": "已导入"})
    assert page.search.text() == ""
    assert page.current_id == imported.id
    assert page.title.text() == imported.name
    assert page.selected == set()
    assert not page.convert.isEnabled(), "导入后仍需勾选，不能隐式操作当前预览"


def test_offscreen_theme_name_width_and_scrollbar_lane(window, qt_app):
    from PySide6.QtCore import QPoint
    page = window.themes
    page.themes = theme_examples(window)
    page.render()
    window.navigation.button(1).click()
    for width in (1000, 1140, 1660):
        window.resize(width, 750)
        qt_app.processEvents()
        assert 100 <= page.table.columnWidth(2) <= 240
        bar = page.table.verticalScrollBar()
        assert bar.isVisible() and bar.width() >= 20
        assert not page.table.scrollDelagate.vScrollBar.isVisible()
        assert bar.mapTo(page.table, QPoint(0, 0)).x() > page.table.viewport().geometry().right()
        header = page.table.horizontalHeader()
        status_right = header.sectionViewportPosition(5) + header.sectionSize(5)
        assert page.table.viewport().width() - status_right >= 8
        assert page.table.horizontalScrollBar().maximum() == 0
        bar.setValue(bar.maximum())
        qt_app.processEvents()
        assert page.table.visualItemRect(page.table.item(70, 2)).intersects(page.table.viewport().rect())
        bar.setValue(0)


def test_offscreen_theme_preview_thumbnails_and_arrows_stay_in_sync(window, qt_app):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    page = window.themes
    samples = theme_examples(window)
    paths = [theme.screenshots[0][0] for theme in samples[:3]]
    samples[0].screenshots = [(paths[index % 3], f"Preview {index + 1}") for index in range(4)]
    samples[1].screenshots = [(paths[1], "Only preview")]
    samples[2].screenshots = []
    page.themes = samples[:3]
    page.render()
    window.navigation.button(1).click()
    window.resize(1000, 650)
    qt_app.processEvents()
    strip = page.screenshot_strip
    assert strip.count() == 4 and strip.currentRow() == 0
    assert all(strip.viewport().rect().contains(strip.visualItemRect(strip.item(index))) for index in range(4))
    QTest.mouseClick(strip.viewport(), Qt.MouseButton.LeftButton, pos=strip.visualItemRect(strip.item(2)).center())
    assert page.screenshot_index == 2 and strip.currentRow() == 2
    assert page.preview._path == str(paths[2])
    assert page.indicator.text().endswith("3 / 4")
    page.next.click()
    assert page.screenshot_index == strip.currentRow() == 3
    page.next.click()
    assert page.screenshot_index == strip.currentRow() == 0
    page.previous.click()
    assert page.screenshot_index == strip.currentRow() == 3
    assert not page.selected, "切换图片不应勾选主题"
    page.table.setCurrentCell(1, 2)
    assert strip.count() == 1 and strip.currentRow() == 0
    assert not page.previous.isEnabled() and not page.next.isEnabled()
    page.table.setCurrentCell(2, 2)
    assert strip.count() == 0 and strip.currentRow() == -1
    assert page.preview.image.isNull()
    page.themes[2].screenshots = [(paths[index % 3], f"Preview {index + 1}") for index in range(10)]
    page.render()
    qt_app.processEvents()
    page.previous.click()
    qt_app.processEvents()
    assert page.screenshot_index == strip.currentRow() == 9
    assert strip.horizontalScrollBar().value() > 0
    assert strip.viewport().rect().contains(strip.visualItemRect(strip.item(9)))


def test_offscreen_theme_thumbnails_scale_together_without_stretching(window, qt_app):
    from PySide6.QtGui import QColor, QImage
    page = window.themes
    samples = theme_examples(window)
    directory = window.store.settings_file.parent / "images"
    ratios = [(1920, 1080), (1200, 900), (900, 1200), (1920, 1080)]
    previews = []
    for index, (width, height) in enumerate(ratios):
        picture = QImage(width, height, QImage.Format.Format_RGB32)
        picture.fill(QColor("#44775f"))
        path = directory / f"aspect-{index}.png"
        assert picture.save(str(path))
        previews.append((path, "Aspect ratio preview"))
    samples[0].screenshots = previews
    page.themes = samples[:1]
    page.render()
    window.navigation.button(1).click()
    strip = page.screenshot_strip
    sizes = []
    for width in (1000, 1440, 2000):
        window.resize(width, 800)
        page.splitter.setSizes([560, width - 750])
        qt_app.processEvents()
        size = strip.iconSize()
        sizes.append((size.width(), size.height(), strip.height()))
        assert size.width() <= 150 and size.height() == round(size.width() * 9 / 16)
        assert strip.height() == size.height() + 28
        assert all(strip.viewport().rect().contains(strip.visualItemRect(strip.item(index))) for index in range(4))
        for index, (source_width, source_height) in enumerate(ratios):
            pixmap = strip.item(index).icon().pixmap(size)
            assert not pixmap.isNull()
            # Rounded pixel dimensions may differ by at most one source-ratio pixel.
            assert abs(pixmap.width() - pixmap.height() * source_width / source_height) <= 1.8
        assert window.grab().save(str(window.store.settings_file.parent / f"thumbnail-scale-{width}.png"))
    assert sizes[0][0] < sizes[-1][0] == 150
    assert sizes[0][1] < sizes[-1][1] and sizes[0][2] < sizes[-1][2]
