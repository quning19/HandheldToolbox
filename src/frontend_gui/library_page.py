"""Library workspace backed by real local/ADB services."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import CheckBox, ComboBox, LineEdit, PrimaryPushButton, PushButton

from library_converter.desktop import convert_library, discover_device, local_target, scan_library
from library_converter.savedeck import convert_savedeck, scan_savedeck
from .appearance import ui_font
from .state import UiStore
from .tasks import TaskHub
from .widgets import ElidedCaption, PlatformGrid, TaskFeedback, caption, heading, panel


class LibraryPage(QWidget):
    def __init__(self, store: UiStore, hub: TaskHub, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.hub = hub
        self.device = None
        self.session = None
        self.generation = 0
        self.scanning = False
        self.setObjectName("libraryPage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 19, 24, 16)
        layout.setSpacing(12)
        layout.addWidget(heading("游戏库转换", "天马 G → ES-DE / SaveDeck · 选择来源后手动加载平台"))
        toolbar, controls = panel()
        first = QHBoxLayout()
        first.setSpacing(10)
        self.source = ComboBox()
        self.source.addItems(["掌机", "电脑目录"])
        self.source.setFixedWidth(114)
        self.source.setAccessibleName("游戏库来源类型")
        first.addWidget(self.source)
        self.frontend = ComboBox()
        self.frontend.addItems(["ES-DE", "SaveDeck"])
        self.frontend.setFixedWidth(116)
        self.frontend.setAccessibleName("目标前端")
        first.addWidget(self.frontend)
        self.paths = QStackedWidget()
        self.paths.setFixedHeight(36)
        self.device_root = ComboBox()
        self.device_root.addItem("点击刷新设备，识别天马 G 目录", userData=None)
        self.device_root.setAccessibleName("天马 G 目录")
        self.paths.addWidget(self.device_root)
        computer = QWidget()
        computer_layout = QHBoxLayout(computer)
        computer_layout.setContentsMargins(0, 0, 0, 0)
        computer_layout.setSpacing(7)
        self.computer_root = LineEdit()
        self.computer_root.setPlaceholderText("选择电脑上的天马 G ROM 目录")
        self.computer_root.setAccessibleName("电脑天马 G 目录")
        computer_layout.addWidget(self.computer_root, 1)
        self.browse = PushButton("浏览…")
        computer_layout.addWidget(self.browse)
        self.paths.addWidget(computer)
        first.addWidget(self.paths, 1)
        self.refresh_device = PushButton("刷新设备")
        first.addWidget(self.refresh_device)
        self.load = PushButton("加载平台")
        first.addWidget(self.load)
        controls.addLayout(first)
        second = QHBoxLayout()
        second.setSpacing(14)
        self.target = ElidedCaption()
        self.target.setMinimumWidth(0)
        second.addWidget(self.target, 1)
        self.shared = CheckBox("共用素材")
        self.shared.setToolTip("核对转换后的副本后更新天马 G 素材引用，并清理不再使用的源素材。默认关闭。")
        self.full = CheckBox("全量覆盖")
        self.full.setToolTip("覆盖来源资料、媒体和启动配置；保留 UUID、收藏及统计。")
        second.addWidget(self.shared)
        second.addWidget(self.full)
        self.start = PrimaryPushButton("开始转换")
        for control in (self.source, self.device_root, self.computer_root, self.browse, self.load, self.start):
            control.setMinimumHeight(36)
        second.addWidget(self.start)
        controls.addLayout(second)
        layout.addWidget(toolbar)
        row = QHBoxLayout()
        self.counts = caption("平台列表 · 尚未加载", tone="accent_ink")
        row.addWidget(self.counts, 1)
        self.select_all = PushButton("全选")
        self.select_none = PushButton("清空选择")
        row.addWidget(self.select_all)
        row.addWidget(self.select_none)
        layout.addLayout(row)
        self.list_stack = QStackedWidget()
        self.list_stack.setMinimumHeight(170)
        self.empty = caption("请选择天马 G 目录，再点击“加载平台”。\n仅点击加载后读取所选来源。")
        self.empty.setFont(ui_font(14))
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.list_stack.addWidget(self.empty)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.grid = PlatformGrid()
        self.grid.set_style(store.card_style)
        self.scroll.setWidget(self.grid)
        self.list_stack.addWidget(self.scroll)
        layout.addWidget(self.list_stack, 1)
        self.feedback = TaskFeedback()
        self.feedback.cancelled.connect(self.hub.cancel)
        layout.addWidget(self.feedback)
        self.source.currentIndexChanged.connect(self._source_changed)
        self.frontend.currentIndexChanged.connect(self.clear_source)
        self.device_root.currentIndexChanged.connect(self.clear_source)
        self.computer_root.textChanged.connect(self.clear_source)
        self.browse.clicked.connect(self._browse)
        self.load.clicked.connect(self.load_platforms)
        self.start.clicked.connect(self.begin_conversion)
        self.refresh_device.clicked.connect(self.discover)
        self.hub.busy_changed.connect(self._busy_changed)
        self.grid.selection_changed.connect(self.update_counts)
        self.full.stateChanged.connect(self.update_counts)
        self.select_all.clicked.connect(lambda: self.grid.select_all(True))
        self.select_none.clicked.connect(lambda: self.grid.select_all(False))
        self.update_target()
        self.update_counts()


    device_changed = Signal(object)

    def source_key(self):
        return self.device_root.currentData() if self.source.currentIndex() == 0 else self.computer_root.text().strip()

    def update_target(self):
        savedeck = self.frontend.currentText() == "SaveDeck"
        self.shared.setVisible(not savedeck)
        if savedeck:
            self.shared.setChecked(False)
        self.full.setText("全量覆盖")
        self.full.setToolTip("默认同步入口增删，已有有效入口跳过。全量覆盖来源资料、媒体和启动配置；保留 UUID、收藏及统计。失效入口移除，媒体不清理。")
        self.start.setText("导出并推送" if savedeck and self.source.currentIndex() == 0 else
                           "导出到原目录" if savedeck else "开始转换")
        if savedeck:
            self.target.setText("输出：" + (str(self.source_key() or "等待选择天马 G 目录")) +
                                " · 共用 ROM，生成 SaveDeck 媒体和配置")
            self.refresh_device.setVisible(self.source.currentIndex() == 0)
            return
        target = self.device.esde_root if self.source.currentIndex() == 0 and self.device else (
            "等待设备识别" if self.source.currentIndex() == 0 else str(
                local_target(self.store.workspace, self.computer_root.text().strip())
                if self.computer_root.text().strip() else self.store.workspace / "library"))
        self.target.setText("输出：" + target)
        self.refresh_device.setVisible(self.source.currentIndex() == 0)

    def _source_changed(self, index):
        self.paths.setCurrentIndex(index)
        self.clear_source()

    def _browse(self):
        from PySide6.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(self, "选择天马 G ROM 目录", self.computer_root.text())
        if path:
            self.computer_root.setText(path)

    def clear_source(self, *_args):
        self.generation += 1
        self.session = None
        if self.scanning:
            self.hub.cancel()
        self.grid.clear()
        self.list_stack.setCurrentIndex(0)
        self.empty.setText("请选择天马 G 目录，再点击“加载平台”。")
        if not self.hub.busy:
            self.feedback.hide()
        self.update_target()
        self.update_counts()

    def reset_workspace(self):
        self.clear_source()

    def discover(self):
        if self.hub.busy:
            return
        self.clear_source()
        self.device = None
        self.device_changed.emit(None)

        def complete(device):
            self.device = device
            self.device_root.blockSignals(True)
            self.device_root.clear()
            for path, count, storage in device.roots:
                self.device_root.addItem(f"{storage} · {path} · {count} 个子目录", userData=path)
            if not device.roots:
                self.device_root.addItem("未发现 rom 或 roms 目录", userData=None)
            self.device_root.blockSignals(False)
            self.device_changed.emit(device)
            self.update_target()
            self.feedback.finish("设备已识别，请选择天马 G 目录后点击“加载平台”。")
            self.update_counts()

        def failed(_message):
            self.device_root.clear()
            self.device_root.addItem("设备未就绪，请刷新", userData=None)
            self.device_changed.emit(None)
            self.update_target()

        self.hub.start(lambda worker: discover_device(), self.feedback, complete, on_error=failed)

    def load_platforms(self):
        if self.hub.busy:
            return
        source = self.source_key()
        device = self.device if self.source.currentIndex() == 0 else None
        if not source or (self.source.currentIndex() == 0 and device is None):
            self.feedback.finish("请先刷新设备并选择目录。" if self.source.currentIndex() == 0 else "请先选择电脑目录。")
            return
        self.clear_source()
        token = self.generation
        self.scanning = True
        self.empty.setText("正在检测平台…")
        workspace, definitions = self.store.workspace, list(self.store.definitions)
        savedeck = self.frontend.currentText() == "SaveDeck"
        scanner = scan_savedeck if savedeck else scan_library

        def item_ready(info):
            if token == self.generation:
                self.grid.append(info)
                self.list_stack.setCurrentIndex(1)
                self.update_counts()

        def complete(session):
            self.scanning = False
            if token != self.generation:
                self.feedback.hide()
                return
            self.session = session
            failures = sum(bool(info.error) for info in session.platforms.values())
            missing = sum(info.missing_references for info in session.platforms.values())
            unlinked = sum(info.unlinked for info in session.platforms.values())
            message = f"{'已取消加载，保留' if session.cancelled else '加载完成：'}{len(session.platforms)} 个平台，{failures} 个平台有问题。"
            self.feedback.finish(message + (f"共用 ROM，生成官方格式媒体与配置；{missing} 个缺失 ROM 入口将排除并报告。" if savedeck else
                                 f"{missing} 个缺失引用，{unlinked} 个 ROM 未关联资料。详情见平台卡片。"))
            self.update_counts()

        def failed(_message):
            self.scanning = False
            self.session = None
            self.update_counts()

        started = self.hub.start(
            lambda worker: scanner(workspace, definitions, source, device,
                                        worker.isInterruptionRequested, worker.progress.emit, worker.item.emit),
            self.feedback, complete, item_ready, failed)
        if not started:
            self.scanning = False

    def update_counts(self, *_args):
        selected = self.grid.selected()
        roms = sum(item.roms for item in selected)
        pending = sum(item.roms if self.full.isChecked() else max(0, item.roms - item.existing) for item in selected)
        self.counts.setText(f"平台 {len(self.grid.cards)} · 已选 {len(selected)} · ROM {roms} · "
                            f"{'处理' if self.full.isChecked() else '新增'} {pending}")
        self.start.setEnabled(bool(selected) and self.session is not None and not self.hub.busy
                              and not any(item.error for item in selected))
        self.select_all.setEnabled(bool(self.grid.cards) and not self.hub.busy)
        self.select_none.setEnabled(bool(self.grid.cards) and not self.hub.busy)

    def _busy_changed(self, busy):
        for widget in (self.load, self.refresh_device, self.shared, self.full, self.grid):
            widget.setEnabled(not busy)
        # Changing a source can cancel this page's scan; writing locks the source.
        for widget in (self.source, self.frontend, self.device_root, self.computer_root, self.browse):
            widget.setEnabled(not busy or self.scanning)
        self.update_counts()

    def begin_conversion(self):
        if self.hub.busy or self.session is None:
            return
        selected = [item.id for item in self.grid.selected()]
        if not selected:
            return
        session = self.session
        full, shared, workspace = self.full.isChecked(), self.shared.isChecked(), self.store.workspace
        savedeck = self.frontend.currentText() == "SaveDeck"
        converter = convert_savedeck if savedeck else convert_library

        def complete(result):
            for card in self.grid.cards:
                if card.item.id in selected:
                    card.item.existing = card.item.roms
                    card.update_details()
            self.session = None
            message = f"{'SaveDeck 导出' if savedeck else '转换'}完成：处理 {result['roms']} 个入口，移除 {result.get('removed', 0)} 个失效入口。输出：{result['output']}。再次转换前请重新加载平台。"
            warnings = result.get("warnings", [])
            if warnings:
                message += " 提示：" + "；".join(warnings)
            self.feedback.finish(message)
            self.update_counts()

        self.hub.start(lambda worker: converter(session, selected, shared, full, workspace,
                                                      worker.isInterruptionRequested, worker.progress.emit),
                       self.feedback, complete)

    def shutdown(self):
        self.hub.cancel()
