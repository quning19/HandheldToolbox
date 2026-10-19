"""Browse themes independently from explicit checkbox-only batch operations."""
from PySide6.QtCore import Qt, QRectF, QSize, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImageReader, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractScrollArea, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QListView, QListWidget, QListWidgetItem, QMenu, QMessageBox, QScrollArea,
    QSizePolicy, QSplitter, QTableWidgetItem, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    CheckBox, ComboBox, IndeterminateProgressBar, PrimaryPushButton, ProgressBar, PushButton,
    SearchLineEdit, TableItemDelegate, TableWidget,
)

from theme_converter.catalog import managed_themes
from theme_converter.service import run_themes, import_original
from .appearance import colors, ui_font
from .state import UiStore
from .tasks import TaskHub
from .widgets import ElidedCaption, caption, panel


def scaled_image(path, size):
    """Ask the image decoder for a bounded image before making a GUI pixmap."""
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    dimensions = reader.size()
    if dimensions.isValid():
        reader.setScaledSize(dimensions.scaled(size, Qt.AspectRatioMode.KeepAspectRatio))
    return QPixmap.fromImage(reader.read())


class ThemePreview(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = QPixmap()
        self._path = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(220, 130)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setToolTip("双击放大原版主题预览")

    def set_image(self, path):
        key = str(path) if path else ""
        if key == self._path:
            return
        self._path = key
        self.image = scaled_image(path, QSize(1600, 1000)) if path else QPixmap()
        self.fit()
        self.updateGeometry()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        ratio = self.image.height() / self.image.width() if not self.image.isNull() else 9 / 16
        return max(130, min(300, round(width * ratio)))

    def sizeHint(self):
        return QSize(320, self.heightForWidth(320))

    def fit(self):
        if self.image.isNull():
            self.setPixmap(QPixmap())
            self.setText("暂无预览")
        else:
            self.setPixmap(self.image.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit()

    def mouseDoubleClickEvent(self, event):
        if not self.image.isNull():
            dialog = QDialog(self)
            dialog.setWindowTitle("原版主题预览")
            dialog.resize(900, 620)
            layout = QVBoxLayout(dialog)
            preview = ThemePreview(dialog)
            preview.image = self.image
            preview.mouseDoubleClickEvent = lambda _event: dialog.accept()
            layout.addWidget(preview)
            dialog.exec()
        super().mouseDoubleClickEvent(event)


class ThemeFeedback(QWidget):
    """One reserved status line; progress never changes the content geometry."""
    cancelled = Signal()

    def __init__(self):
        super().__init__()
        self.setFixedHeight(32)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.message = ElidedCaption()
        row.addWidget(self.message, 1)
        self.bar = ProgressBar(useAni=False)
        self.bar.setFixedSize(150, 6)
        row.addWidget(self.bar)
        self.wait_bar = IndeterminateProgressBar(start=False)
        self.wait_bar.setFixedSize(150, 6)
        row.addWidget(self.wait_bar)
        self.percent = caption("")
        self.percent.setFixedWidth(54)
        self.percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.percent)
        self.stop = PushButton("取消")
        self.stop.setFixedHeight(28)
        self.stop.clicked.connect(self.cancelled)
        row.addWidget(self.stop)
        self.finish("就绪 · 勾选主题后可下载、转换或上传")

    def update_progress(self, text, value, cancellable=True):
        self.message.setText(text)
        unknown = value < 0
        self.bar.setVisible(not unknown)
        self.wait_bar.setVisible(unknown)
        if unknown:
            if not self.wait_bar.isStarted():
                self.wait_bar.start()
        else:
            self.wait_bar.stop()
            self.bar.setValue(value)
        self.percent.setText("处理中" if unknown else f"{value}%")
        self.percent.show()
        self.stop.setVisible(cancellable)
        self.show()

    def finish(self, text):
        self.message.setText(text)
        self.bar.hide()
        self.wait_bar.stop()
        self.wait_bar.hide()
        self.percent.hide()
        self.stop.hide()
        self.show()


class ThemeDelegate(TableItemDelegate):
    """Fluent rows with larger framed status icons, painted without cell widgets."""
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        tone = index.data(Qt.ItemDataRole.UserRole + 1) or "ink"
        color = QColor(colors()[tone])
        option.palette.setColor(QPalette.ColorRole.Text, color)
        option.palette.setColor(QPalette.ColorRole.HighlightedText, color)
        if index.column() >= 3 and index.data(Qt.ItemDataRole.DisplayRole) not in {"—", "×"}:
            option.text = ""  # Keep the model's symbol for accessibility and tooltips.

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if index.column() < 3 or index.data(Qt.ItemDataRole.DisplayRole) in {"—", "×"}:
            return
        palette = colors()
        tone = index.data(Qt.ItemDataRole.UserRole + 1) or "muted"
        foreground = QColor(palette[tone])
        background = QColor(palette.get(tone + "_soft", palette["raised"]))
        rect = QRectF(0, 0, 28, 28)
        rect.moveCenter(QRectF(option.rect).center())
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(background)
        painter.setPen(QPen(foreground, 1.3))
        painter.drawRoundedRect(rect, 5, 5)
        painter.setFont(ui_font(22, QFont.Weight.DemiBold))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, index.data(Qt.ItemDataRole.DisplayRole) or "")
        painter.restore()


class ThemeTable(TableWidget):
    """Bound names and reserve a real scrollbar lane outside the table viewport."""
    def __init__(self):
        super().__init__()
        # Fluent normally overlays its scrollbar on the last status column.
        self.scrollDelagate.vScrollBar.setForceHidden(True)
        QAbstractScrollArea.setVerticalScrollBarPolicy(self, Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.verticalScrollBar().setFixedWidth(20)
        self.verticalScrollBar().setStyleSheet("""
            QScrollBar:vertical { background: transparent; width: 20px; margin: 4px; }
            QScrollBar::handle:vertical { background: palette(mid); min-height: 28px; border-radius: 4px; }
            QScrollBar::handle:vertical:hover { background: palette(text); }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.columnCount() == 6:
            fixed = sum(self.columnWidth(column) for column in (0, 1, 3, 4, 5))
            self.setColumnWidth(2, max(100, min(240, self.viewport().width() - fixed - 8)))


class ScreenshotStrip(QListWidget):
    """One row of clickable previews; four fit even in the narrow detail pane."""
    def __init__(self):
        super().__init__()
        self.setObjectName("themeScreenshots")
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setMovement(QListView.Movement.Static)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setWrapping(False)
        self.setSpacing(0)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(64)
        self.setAccessibleName("主题预览缩略图，点击切换大图")
        self.setStyleSheet("""
            QListWidget#themeScreenshots { border: 0; background: transparent; outline: 0; }
            QListWidget#themeScreenshots::item { border: 2px solid transparent; border-radius: 4px; padding: 2px; }
            QListWidget#themeScreenshots::item:selected { border-color: palette(highlight); background: palette(alternate-base); }
        """)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = max(44, min(160, self.viewport().width() // 4))
        image_width = width - 10
        image_height = round(image_width * 9 / 16)
        self.setGridSize(QSize(width, image_height + 10))
        self.setIconSize(QSize(image_width, image_height))
        # Reserve the horizontal scrollbar lane even when all four images fit.
        height = image_height + 28
        if self.height() != height:
            self.setFixedHeight(height)


def theme_symbols(theme):
    """Return symbol, accessible description and palette tone for each column."""
    if theme.original:
        original = (("↑", "官方原版有更新", "warning") if theme.update_available else
                    ("✓", "已下载" if theme.repository else "本地导入", "success"))
        if theme.update_error:
            original = ("!", "更新检查失败：" + theme.update_error, "warning")
        elif theme.repository and theme.update_available is None:
            original = ("✓", "已下载；尚未检查更新", "success")
    else:
        original = ("—", "未下载原版", "muted")
    if theme.converted:
        converted = ("✓", "已转换，可上传", "success")
    elif theme.stale:
        converted = ("↻", "需要重新转换：" + theme.reason, "warning")
    elif theme.reason and theme.original:
        converted = ("!", "转换或原版读取失败：" + theme.reason, "warning")
    else:
        converted = ("—", "未转换", "muted")
    device = (("—", "设备未连接或尚未检查", "muted") if theme.device is None else
              ("✓", "设备已有适配主题，仅表示存在", "success") if theme.device else
              ("×", "设备未发现适配主题", "muted"))
    return original, converted, device


class ThemesPage(QWidget):
    def __init__(self, store: UiStore, hub: TaskHub) -> None:
        super().__init__()
        self.store, self.hub = store, hub
        self.device = None
        self.themes = managed_themes(store.workspace, store.definitions)
        self.selected: set[str] = set()
        self.current_id = ""
        self.screenshot_index = 0
        self._rows = {}
        self._thumbnail_cache = {}
        self._details_id = None
        self.setObjectName("themesPage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 12)
        layout.setSpacing(10)
        header = QHBoxLayout()
        title = QLabel("主题管理")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.catalog = PushButton("刷新目录")
        self.check_updates = PushButton("检查更新")
        self.refresh = PushButton("刷新设备")
        self.page_more = PushButton("⋯")
        self.page_more.setFixedWidth(36)
        self.page_more.setAccessibleName("页面更多操作")
        page_menu = QMenu(self.page_more)
        self.import_button = page_menu.addAction("导入本地主题…")
        self.page_more.setMenu(page_menu)
        self.global_buttons = (self.catalog, self.check_updates, self.refresh, self.page_more)
        for button in self.global_buttons:
            header.addWidget(button)
        layout.addLayout(header)
        filters = QHBoxLayout()
        self.search = SearchLineEdit()
        self.search.setPlaceholderText("搜索主题名称")
        filters.addWidget(self.search, 1)
        self.original_filter = ComboBox()
        self.original_filter.addItems(["原版：全部", "未下载", "已下载", "有更新", "本地导入"])
        self.converted_filter = ComboBox()
        self.converted_filter.addItems(["适配：全部", "未转换", "已转换", "需重转"])
        self.device_filter = ComboBox()
        self.device_filter.addItems(["设备：全部", "已有", "无"])
        for widget in (self.original_filter, self.converted_filter, self.device_filter):
            widget.setMinimumWidth(98)
            filters.addWidget(widget)
            widget.currentIndexChanged.connect(self.filter_changed)
        self.search.textChanged.connect(self.filter_changed)
        self.reset = PushButton("重置")
        self.reset.clicked.connect(self.reset_filters)
        filters.addWidget(self.reset)
        self.counts = caption("")
        filters.addWidget(self.counts)
        layout.addLayout(filters)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        left = QWidget()
        left.setMinimumWidth(440)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        self.batch_bar = QWidget()
        selection = QHBoxLayout(self.batch_bar)
        selection.setContentsMargins(2, 0, 0, 0)
        selection.setSpacing(6)
        self.select_visible = CheckBox("全选")
        self.select_visible.clicked.connect(lambda checked: self.select_all(checked))
        selection.addWidget(self.select_visible)
        self.selection_count = caption("已选 0")
        selection.addWidget(self.selection_count)
        selection.addStretch(1)
        self.download = PrimaryPushButton("下载/更新")
        self.convert = PushButton("转换")
        self.upload = PushButton("上传设备")
        self.more = PushButton("更多")
        batch_menu = QMenu(self.more)
        self.download_convert = batch_menu.addAction("下载／更新并转换勾选主题")
        batch_menu.addSeparator()
        self.delete_original = batch_menu.addAction("删除勾选主题的本地原版…")
        self.delete_output = batch_menu.addAction("删除勾选主题的转换结果…")
        self.more.setMenu(batch_menu)
        for button in (self.download, self.convert, self.upload, self.more):
            selection.addWidget(button)
        left_layout.addWidget(self.batch_bar)
        self.table = ThemeTable()
        self.table.setItemDelegate(ThemeDelegate(self.table))
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["", "预览", "主题名称", "原版", "适配", "设备"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        self.table.setIconSize(QSize(80, 46))
        self.table.setWordWrap(False)
        table_header = self.table.horizontalHeader()
        table_header.setFixedHeight(34)
        table_header.setStyleSheet("QHeaderView::section { padding: 4px 6px; }")
        table_header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for column, width in ((0, 40), (1, 92), (3, 48), (4, 48), (5, 48)):
            table_header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(column, width)
            if column >= 3:
                self.table.horizontalHeaderItem(column).setToolTip("悬停各行符号查看完整状态")
        table_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 220)
        self.table.itemChanged.connect(self._selection_changed)
        self.table.currentCellChanged.connect(self.current_changed)
        left_layout.addWidget(self.table, 1)
        self.empty = caption("")
        self.empty.setWordWrap(True)
        left_layout.addWidget(self.empty)
        self.splitter.addWidget(left)
        self.details, detail = panel()
        self.details.setMinimumWidth(280)
        detail.setContentsMargins(16, 14, 16, 12)
        detail.setSpacing(10)
        self.title = QLabel("选择主题查看预览")
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setFont(ui_font(17, QFont.Weight.DemiBold))
        self.title.setWordWrap(True)
        detail.addWidget(self.title)
        self.author = ElidedCaption()
        detail.addWidget(self.author)
        self.preview = ThemePreview()
        self.preview.setMinimumHeight(100)
        detail.addWidget(self.preview)
        self.screenshot_strip = ScreenshotStrip()
        self.screenshot_strip.currentRowChanged.connect(self.select_screenshot)
        detail.addWidget(self.screenshot_strip)
        paging = QHBoxLayout()
        self.previous, self.next = PushButton("‹"), PushButton("›")
        self.previous.setFixedSize(30, 28)
        self.next.setFixedSize(30, 28)
        self.previous.setAccessibleName("上一张原版预览")
        self.next.setAccessibleName("下一张原版预览")
        self.indicator = caption("原版预览")
        paging.addWidget(self.previous)
        paging.addWidget(self.indicator, 1, Qt.AlignmentFlag.AlignCenter)
        paging.addWidget(self.next)
        detail.addLayout(paging)
        self.previous.clicked.connect(lambda: self.change_screenshot(-1))
        self.next.clicked.connect(lambda: self.change_screenshot(1))
        self.screenshot_caption = ElidedCaption()
        self.screenshot_caption.setTextFormat(Qt.TextFormat.PlainText)
        detail.addWidget(self.screenshot_caption)
        self.description = caption("")
        self.description.setTextFormat(Qt.TextFormat.PlainText)
        self.description.setWordWrap(True)
        self.description.setMaximumHeight(58)
        detail.addWidget(self.description)
        self.details_button = PushButton("主题资料…")
        self.details_button.clicked.connect(self.show_metadata)
        detail.addWidget(self.details_button, 0, Qt.AlignmentFlag.AlignLeft)
        detail.addStretch(1)
        self.splitter.addWidget(self.details)
        self.splitter.setSizes([560, 380])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        layout.addWidget(self.splitter, 1)
        self.feedback = ThemeFeedback()
        self.feedback.cancelled.connect(self.hub.cancel)
        layout.addWidget(self.feedback)
        self.catalog.clicked.connect(lambda: self.begin("catalog"))
        self.check_updates.clicked.connect(lambda: self.begin("check-updates"))
        self.refresh.clicked.connect(lambda: self.begin("refresh"))
        self.import_button.triggered.connect(self.import_local)
        self.download.clicked.connect(lambda: self.begin("download"))
        self.download_convert.triggered.connect(lambda: self.begin("download-convert"))
        self.convert.clicked.connect(lambda: self.begin("convert"))
        self.upload.clicked.connect(lambda: self.begin("upload"))
        self.delete_original.triggered.connect(lambda: self.confirm_delete("delete-original"))
        self.delete_output.triggered.connect(lambda: self.confirm_delete("delete-output"))
        self.hub.busy_changed.connect(self.update_actions)
        self.update_paths()
        self.render()

    def update_paths(self):
        target = self.device.esde_root + "/themes" if self.device else "尚未连接设备"
        self.page_more.setToolTip(f"工作目录：{self.store.workspace}\n原版：themes/original\n结果：themes/exported\n上传目标：{target}")

    def set_device(self, device):
        self.device = device
        for theme in self.themes:
            theme.device = None
        self.update_paths()
        self.render()

    def visible_themes(self):
        query = self.search.text().strip().casefold()
        original, converted, device = (widget.currentIndex() for widget in
                                      (self.original_filter, self.converted_filter, self.device_filter))
        return [theme for theme in self.themes
                if (not query or query in theme.name.casefold())
                and (original == 0 or (original == 1 and not theme.original)
                     or (original == 2 and theme.original and bool(theme.repository))
                     or (original == 3 and theme.update_available is True)
                     or (original == 4 and theme.original and not theme.repository))
                and (converted == 0 or (converted == 1 and not theme.converted and not theme.stale)
                     or (converted == 2 and theme.converted) or (converted == 3 and theme.stale))
                and (device == 0 or (device == 1 and theme.device is True) or (device == 2 and theme.device is False))]

    def filter_changed(self, *_args):
        self.selected.clear()
        self._sync_checks()
        self.apply_filter()

    def reset_filters(self):
        widgets = (self.search, self.original_filter, self.converted_filter, self.device_filter)
        for widget in widgets:
            widget.blockSignals(True)
        self.search.clear()
        for widget in widgets[1:]:
            widget.setCurrentIndex(0)
        for widget in widgets:
            widget.blockSignals(False)
        self.filter_changed()

    def thumbnail(self, path, size=None):
        size = size or QSize(80, 46)
        try:
            stat = path.stat()
            key = (str(path), stat.st_size, stat.st_mtime_ns, size.width(), size.height())
        except OSError:
            return QIcon()
        if key not in self._thumbnail_cache:
            self._thumbnail_cache[key] = QIcon(scaled_image(path, size))
        return self._thumbnail_cache[key]

    def render(self):
        """Rebuild only when business data changes, never on search or selection."""
        self._rows = {theme.id: row for row, theme in enumerate(self.themes)}
        self.selected.intersection_update(self._rows)
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        self.table.clearContents()
        self.table.setRowCount(len(self.themes))
        for row, theme in enumerate(self.themes):
            check = QTableWidgetItem()
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            if not self.hub.busy:
                flags |= Qt.ItemFlag.ItemIsUserCheckable
            check.setFlags(flags)
            check.setCheckState(Qt.CheckState.Checked if theme.id in self.selected else Qt.CheckState.Unchecked)
            check.setData(Qt.ItemDataRole.UserRole, theme.id)
            check.setToolTip("勾选后操作：" + theme.name)
            self.table.setItem(row, 0, check)
            thumbnail = QTableWidgetItem()
            if theme.screenshots:
                thumbnail.setIcon(self.thumbnail(theme.screenshots[0][0]))
            thumbnail.setToolTip("点击行查看原版预览")
            self.table.setItem(row, 1, thumbnail)
            name = QTableWidgetItem(theme.name)
            name.setToolTip(theme.name)
            name.setFont(ui_font(14, QFont.Weight.DemiBold))
            self.table.setItem(row, 2, name)
            for column, (symbol, explanation, tone) in enumerate(theme_symbols(theme), 3):
                item = QTableWidgetItem(symbol)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                item.setFont(ui_font(18 if symbol in {"—", "×"} else 22, QFont.Weight.DemiBold))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setData(Qt.ItemDataRole.UserRole + 1, tone)
                item.setData(Qt.ItemDataRole.AccessibleTextRole, explanation)
                item.setToolTip(explanation + ("\n检查时间：" + theme.checked if column == 3 and theme.checked else ""))
                self.table.setItem(row, column, item)
            self.table.setRowHeight(row, 64)
        self.table.blockSignals(False)
        self._details_id = None
        self.preview._path = None  # A catalogue refresh can replace an image at the same path.
        self.apply_filter()
        self.table.setUpdatesEnabled(True)

    def apply_filter(self):
        visible = self.visible_themes()
        identities = {theme.id for theme in visible}
        self.selected.intersection_update(identities)
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        for identity, row in self._rows.items():
            self.table.setRowHidden(row, identity not in identities)
        if self.current_id not in identities:
            self.current_id = visible[0].id if visible else ""
            self.screenshot_index = 0
        if self.current_id:
            self.table.setCurrentCell(self._rows[self.current_id], 2)
        else:
            self.table.setCurrentItem(None)
            self.table.clearSelection()
        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self.empty.setVisible(not visible)
        self.empty.setText("没有符合条件的主题，调整筛选或点击重置。" if self.themes else "点击“刷新目录”获取官方主题。")
        self.show_details()
        self.update_actions()

    def current_changed(self, row, _column, _previous_row, _previous_column):
        if row < 0 or self.table.item(row, 0) is None:
            return
        identity = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if identity != self.current_id:
            self.current_id = identity
            self.screenshot_index = 0
            self.show_details()

    def current_theme(self):
        return next((theme for theme in self.themes if theme.id == self.current_id), None)

    def show_details(self):
        if self._details_id == self.current_id:
            return
        self._details_id = self.current_id
        theme = self.current_theme()
        self.title.setText(theme.name if theme else "选择主题查看预览")
        self.author.setText("作者 · " + theme.author if theme and theme.author else "ES-DE 原版主题预览" if theme else "")
        summary = []
        if theme:
            if theme.aspect_ratios:
                summary.append("比例 · " + " / ".join(theme.aspect_ratios))
            summary.append(f"变体 {len(theme.variants)} · 配色 {len(theme.color_schemes)}")
        self.description.setText("\n".join(summary))
        self.description.setToolTip("\n".join(summary))
        self.details_button.setEnabled(theme is not None)
        self.screenshot_strip.blockSignals(True)
        self.screenshot_strip.clear()
        if theme:
            for index, (path, text) in enumerate(theme.screenshots):
                item = QListWidgetItem(self.thumbnail(path, QSize(150, 84)), "")
                item.setToolTip(f"预览 {index + 1}：{text}")
                item.setData(Qt.ItemDataRole.AccessibleTextRole, f"预览 {index + 1}：{text}")
                self.screenshot_strip.addItem(item)
        self.screenshot_strip.blockSignals(False)
        self.change_screenshot(0)

    def show_metadata(self):
        theme = self.current_theme()
        if theme is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(theme.name + " · 主题资料")
        dialog.resize(520, 440)
        layout = QVBoxLayout(dialog)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        text = QLabel()
        text.setTextFormat(Qt.TextFormat.PlainText)
        text.setWordWrap(True)
        text.setAlignment(Qt.AlignmentFlag.AlignTop)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lines = [theme.name, "作者：" + (theme.author or "未提供")]
        for label, values in (("宽高比", theme.aspect_ratios), ("变体", theme.variants), ("配色", theme.color_schemes)):
            if values:
                lines.append(label + "：" + "、".join(values))
        lines.extend(explanation for _symbol, explanation, _tone in theme_symbols(theme))
        if theme.checked:
            lines.append("检查时间：" + theme.checked)
        if theme.deprecated:
            lines.append("官方已标记弃用或不再收录，本地文件保留。")
        if theme.reason:
            lines.append(theme.reason)
        text.setText("\n\n".join(lines))
        scroll.setWidget(text)
        layout.addWidget(scroll)
        close = PushButton("关闭")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        dialog.exec()

    def change_screenshot(self, offset):
        theme = self.current_theme()
        screenshots = theme.screenshots if theme else []
        self.screenshot_index = (self.screenshot_index + offset) % len(screenshots) if screenshots else 0
        path, text = screenshots[self.screenshot_index] if screenshots else (None, "")
        self.preview.set_image(path)
        self.screenshot_caption.setText(text)
        self.indicator.setText(f"原版预览  {self.screenshot_index + 1} / {len(screenshots)}" if screenshots else "暂无原版预览")
        self.previous.setEnabled(len(screenshots) > 1)
        self.next.setEnabled(len(screenshots) > 1)
        self.screenshot_strip.blockSignals(True)
        self.screenshot_strip.setCurrentRow(self.screenshot_index if screenshots else -1)
        if screenshots:
            self.screenshot_strip.scrollToItem(self.screenshot_strip.currentItem(), QAbstractItemView.ScrollHint.PositionAtCenter)
        self.screenshot_strip.blockSignals(False)

    def select_screenshot(self, index):
        theme = self.current_theme()
        if theme and 0 <= index < len(theme.screenshots):
            self.screenshot_index = index
            self.change_screenshot(0)

    def _selection_changed(self, item):
        if item.column() != 0:
            return
        if self.hub.busy:
            self._sync_checks()
            return
        identity = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self.selected.add(identity)
        else:
            self.selected.discard(identity)
        self.update_actions()

    def _sync_checks(self):
        self.table.blockSignals(True)
        for identity, row in self._rows.items():
            self.table.item(row, 0).setCheckState(Qt.CheckState.Checked if identity in self.selected else Qt.CheckState.Unchecked)
        self.table.blockSignals(False)

    def select_all(self, checked):
        if self.hub.busy:
            return
        self.selected = {theme.id for theme in self.visible_themes()} if checked else set()
        self._sync_checks()
        self.update_actions()

    def action_themes(self):
        return [theme for theme in self.themes if theme.id in self.selected]

    def update_actions(self, *_args):
        selected, busy = self.action_themes(), self.hub.busy
        visible = self.visible_themes()
        self.counts.setText(f"{len(visible)} / {len(self.themes)} 个主题")
        self.selection_count.setText(f"已选 {len(selected)} 个")
        self.select_visible.blockSignals(True)
        self.select_visible.setCheckState(Qt.CheckState.Unchecked if not selected else
                                         Qt.CheckState.Checked if len(selected) == len(visible) else Qt.CheckState.PartiallyChecked)
        self.select_visible.blockSignals(False)
        self.select_visible.setEnabled(bool(visible) and not busy)
        downloadable = bool(selected) and all(theme.repository for theme in selected) and not busy
        self.download.setEnabled(downloadable)
        self.download_convert.setEnabled(downloadable)
        originals = bool(selected) and all(theme.original for theme in selected)
        self.convert.setEnabled(originals and not busy)
        self.upload.setEnabled(bool(selected) and all(theme.converted for theme in selected) and self.device is not None and not busy)
        self.delete_original.setEnabled(originals and not busy)
        self.delete_output.setEnabled(bool(selected) and all(theme.output and theme.output.is_dir() for theme in selected) and not busy)
        self.more.setEnabled(bool(selected) and not busy)
        count = len(selected)
        scope = f"操作勾选的 {count} 个主题。" if count else "请先勾选要操作的主题；点击行只切换预览。"
        self.download.setToolTip(scope + ("包含本地导入主题，无法在线更新。" if selected and not downloadable and not busy else "下载缺少的官方原版，更新已下载的原版。"))
        self.convert.setToolTip(scope + ("请先下载所有勾选主题的原版。" if selected and not originals else "生成 ES-DE 使用的天马G目录适配结果。"))
        self.upload.setToolTip(scope + ("请先连接设备。" if self.device is None else
                                       "请先转换全部勾选主题。" if not all(theme.converted for theme in selected) else
                                       "上传有效结果，覆盖同名文件，不清除设备多余文件。"))
        self.batch_bar.setToolTip(scope)
        for button in self.global_buttons:
            button.setEnabled(not busy)
        self.refresh.setEnabled(self.device is not None and not busy)
        self.refresh.setToolTip("读取当前设备上的适配主题状态" if self.device else "请先从游戏库页面连接设备")
        self.check_updates.setEnabled(any(theme.original and theme.repository for theme in self.themes) and not busy)
        self.check_updates.setToolTip("检查所有已下载的官方主题，不下载更新")
        self.import_button.setEnabled(not busy)
        # Keep scrolling and preview navigation available throughout downloads.
        # Only the batch selection is locked to the identities captured at start.
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            flags = item.flags()
            updated = flags & ~Qt.ItemFlag.ItemIsUserCheckable if busy else flags | Qt.ItemFlag.ItemIsUserCheckable
            if updated != flags:
                item.setFlags(updated)
        self.table.blockSignals(False)
        for widget in (self.search, self.original_filter, self.converted_filter, self.device_filter, self.reset):
            widget.setEnabled(not busy)

    def import_local(self):
        if self.hub.busy:
            return
        directory = QFileDialog.getExistingDirectory(self, "选择含 capabilities.xml 的本地原版主题目录")
        if not directory:
            return
        workspace, definitions = self.store.workspace, list(self.store.definitions)
        def operation(worker):
            identity = import_original(workspace, directory, worker.isInterruptionRequested, worker.progress.emit)
            return {"themes": managed_themes(workspace, definitions), "message": "原版主题已导入。", "identity": identity}
        self.hub.start(operation, self.feedback, self.completed)

    def confirm_delete(self, operation):
        selected = self.action_themes()
        if not selected or self.hub.busy:
            return
        label = "原版" if operation == "delete-original" else "转换结果"
        paths = [theme.source if operation == "delete-original" else theme.output for theme in selected]
        message = f"移除勾选的 {len(selected)} 个主题的本地{label}，文件将保留在备份中：\n\n" + "\n".join(map(str, paths))
        message += "\n\n设备内容不会删除。" + ("保留的转换结果将标记为需重转。" if operation == "delete-original" else "")
        if QMessageBox.question(self, "删除勾选主题的本地" + label, message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.begin(operation)

    def completed(self, result):
        old_device = {theme.id: (theme.output_name or theme.name + "_天马G", theme.device) for theme in self.themes}
        self.themes = result if isinstance(result, list) else result["themes"]
        if not isinstance(result, list) and not result.get("device_refreshed"):
            for theme in self.themes:
                target, present = old_device.get(theme.id, ("", None))
                if target == (theme.output_name or theme.name + "_天马G"):
                    theme.device = present
        if isinstance(result, dict) and result.get("identity"):
            self.render()
            self.reset_filters()
            self.current_id = result["identity"]
            self.screenshot_index = 0
            self.apply_filter()
        else:
            self.render()
        self.feedback.finish("设备主题状态已刷新。" if isinstance(result, list) else result["message"])

    def begin(self, operation):
        if self.hub.busy:
            return
        workspace, definitions = self.store.workspace, list(self.store.definitions)
        identities = [theme.id for theme in self.action_themes()]
        if operation in {"catalog", "check-updates", "refresh"}:
            identities = []
        elif not identities:
            return
        device = self.device
        if operation in {"refresh", "upload"}:
            for theme in self.themes:
                theme.device = None
            self.render()
        def failed(_message):
            self.themes = managed_themes(workspace, definitions)
            self.render()
        started = self.hub.start(lambda worker: run_themes(operation, workspace, definitions, identities, device,
                                                          worker.isInterruptionRequested, worker.progress.emit),
                                 self.feedback, self.completed, on_error=failed)
        if started:
            text = {"catalog": "正在刷新官方目录与预览…", "check-updates": "正在检查已下载主题的更新…",
                    "refresh": "正在读取设备主题状态…"}.get(operation, f"正在处理勾选的 {len(identities)} 个主题…")
            self.feedback.update_progress(text, -1)

    def cancel_operation(self):
        self.hub.cancel()

    def reset_workspace(self):
        self.themes = managed_themes(self.store.workspace, self.store.definitions)
        self.selected.clear()
        self.current_id = ""
        self._thumbnail_cache.clear()
        self.update_paths()
        self.render()
        self.reset_filters()
        self.feedback.finish("就绪 · 勾选主题后可下载、转换或上传")
