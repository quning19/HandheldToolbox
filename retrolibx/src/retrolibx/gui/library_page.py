"""Library workspace with cancellable example loading and native platform cards."""

from dataclasses import replace

from PySide6.QtCore import QThread, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import CheckBox, ComboBox, LineEdit, PrimaryPushButton, PushButton

from .state import PlatformPreview, UiStore, example_platforms
from .appearance import ui_font
from .widgets import ElidedCaption, PlatformGrid, TaskFeedback, caption, heading, panel


class ExamplePlatformLoader(QThread):
    platform_ready = Signal(int, object)
    loaded = Signal(int)

    def __init__(self, token: int, items: list[PlatformPreview], parent: QWidget) -> None:
        super().__init__(parent)
        self.token, self.items = token, items

    def run(self) -> None:
        for item in self.items:
            if self.isInterruptionRequested():
                break
            self.msleep(150)
            if self.isInterruptionRequested():
                break
            self.platform_ready.emit(self.token, item)
        self.loaded.emit(self.token)


class LibraryPage(QWidget):
    def __init__(self, store: UiStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self._token = 0
        self._workers: set[ExamplePlatformLoader] = set()
        self.loading = False
        self.running = False
        self._history: dict[tuple[str, str], int] = {}
        self._queue: list[PlatformPreview] = []
        self._processed = 0
        self._planned = 0
        self.setObjectName("libraryPage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 19, 24, 16)
        layout.setSpacing(12)
        layout.addWidget(heading("游戏库转换", "天马 G → ES-DE · 选择来源后手动加载平台"))
        toolbar, controls = panel()
        first = QHBoxLayout()
        first.setSpacing(10)
        self.source = ComboBox()
        self.source.addItems(["掌机", "电脑目录"])
        self.source.setFixedWidth(114)
        self.source.setAccessibleName("游戏库来源类型")
        first.addWidget(self.source)
        self.paths = QStackedWidget()
        self.paths.setFixedHeight(36)
        self.device_root = ComboBox()
        self.device_root.addItem("SD 卡 · /storage/示例SD/Roms · 15 个子目录", userData="sd")
        self.device_root.addItem("内置存储 · /storage/emulated/0/roms · 4 个子目录", userData="internal")
        self.device_root.setAccessibleName("天马 G 目录（示例）")
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
        self.load = PushButton("加载平台")
        first.addWidget(self.load)
        controls.addLayout(first)
        second = QHBoxLayout()
        second.setSpacing(14)
        self.target = ElidedCaption()
        self.target.setMinimumWidth(0)
        second.addWidget(self.target, 1)
        self.shared = CheckBox("共用素材")
        self.shared.setToolTip("正式接入后：共用转换后的封面、Logo 和视频。默认关闭。")
        self.full = CheckBox("全量替换")
        self.full.setToolTip("重新处理已识别入口和对应素材；不清空目标或删除额外条目。")
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
        self.empty = caption("请选择天马 G 目录，再点击“加载平台”。\n此版使用示例数据，不读取实际目录或设备。")
        self.empty.setFont(ui_font(14))
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.list_stack.addWidget(self.empty)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.grid = PlatformGrid()
        self.scroll.setWidget(self.grid)
        self.list_stack.addWidget(self.scroll)
        layout.addWidget(self.list_stack, 1)
        self.feedback = TaskFeedback()
        self.feedback.cancelled.connect(self.cancel_operation)
        layout.addWidget(self.feedback)
        self.timer = QTimer(self)
        self.timer.setInterval(260)
        self.timer.timeout.connect(self._convert_next)
        self.source.currentIndexChanged.connect(self._source_changed)
        self.device_root.currentIndexChanged.connect(self.clear_source)
        self.computer_root.textChanged.connect(self.clear_source)
        self.browse.clicked.connect(self._browse)
        self.load.clicked.connect(self.load_platforms)
        self.start.clicked.connect(self.begin_conversion)
        self.grid.selection_changed.connect(self.update_counts)
        self.full.stateChanged.connect(self.update_counts)
        self.select_all.clicked.connect(lambda: self.grid.select_all(True))
        self.select_none.clicked.connect(lambda: self.grid.select_all(False))
        self.update_target()
        self.update_counts()

    def source_key(self) -> str:
        return str(self.device_root.currentData()) if self.source.currentIndex() == 0 else "computer:" + self.computer_root.text().strip()

    def update_target(self) -> None:
        target = "内置存储 · ES-DE（示例）" if self.source.currentIndex() == 0 else str(self.store.workspace / "library")
        self.target.setText("输出：" + target)
        self.target.setToolTip(target)

    def _source_changed(self, index: int) -> None:
        self.paths.setCurrentIndex(index)
        self.clear_source()

    def _browse(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(self, "选择天马 G ROM 目录", self.computer_root.text())
        if path:
            self.computer_root.setText(path)

    def clear_source(self, *_args) -> None:
        self.cancel_operation()
        self.grid.clear()
        self.list_stack.setCurrentIndex(0)
        self.empty.setText("来源已更新，请点击“加载平台”。\n只在点击后加载，当前使用示例数据。")
        self.feedback.hide()
        self.update_target()
        self.update_counts()

    def reset_workspace(self) -> None:
        self._history.clear()
        self.clear_source()

    def cancel_operation(self) -> None:
        self._token += 1
        for worker in self._workers:
            worker.requestInterruption()
        if self.loading:
            self.feedback.finish("已取消加载，已显示的平台可继续选择。")
        if self.running:
            self.feedback.finish(f"已取消示例转换，已完成 {self._processed}/{self._planned} 个入口。未操作实际文件。")
        self.timer.stop()
        self.loading = self.running = False
        self._lock_inputs(False)
        self.update_counts()

    def load_platforms(self) -> None:
        if self.source.currentIndex() == 1 and not self.computer_root.text().strip():
            self.feedback.finish("请先选择电脑上的天马 G 目录。")
            return
        self.cancel_operation()
        self.grid.clear()
        self.list_stack.setCurrentIndex(0)
        self.empty.setText("正在加载平台…")
        self.loading = True
        items = example_platforms(self.store.definitions, self.source_key())
        self._total = len(items)
        self.feedback.update_progress("正在加载示例平台…", 0)
        worker = ExamplePlatformLoader(self._token, items, self)
        self._workers.add(worker)
        worker.platform_ready.connect(self._platform_ready)
        worker.loaded.connect(self._loaded)
        worker.finished.connect(lambda w=worker: self._workers.discard(w))
        worker.finished.connect(worker.deleteLater)
        worker.start()
        self.load.setText("重新加载")
        self.update_counts()

    @Slot(int, object)
    def _platform_ready(self, token: int, item: PlatformPreview) -> None:
        if token != self._token:
            return
        item = replace(item, existing=self._history.get((self.source_key(), item.id), item.existing))
        self.grid.append(item)
        self.list_stack.setCurrentIndex(1)
        self.feedback.update_progress(f"已加载 {len(self.grid.cards)}/{self._total} 个示例平台", int(100 * len(self.grid.cards) / max(1, self._total)))
        self.update_counts()

    @Slot(int)
    def _loaded(self, token: int) -> None:
        if token != self._token:
            return
        self.loading = False
        self.load.setText("加载平台")
        if not self.grid.cards:
            self.empty.setText("该来源暂无示例平台。新增平台的真实扫描将在业务接入后实现。")
        self.feedback.hide()
        self.update_counts()

    def update_counts(self, *_args) -> None:
        selected = self.grid.selected()
        roms = sum(item.roms for item in selected)
        pending = sum(item.roms if self.full.isChecked() else max(0, item.roms - item.existing) for item in selected)
        self.counts.setText(f"平台 {len(self.grid.cards)} · 已选 {len(selected)} · ROM {roms} · {'处理' if self.full.isChecked() else '新增'} {pending}")
        self.start.setEnabled(bool(selected) and not self.loading and not self.running)
        self.select_all.setEnabled(bool(self.grid.cards) and not self.running)
        self.select_none.setEnabled(bool(self.grid.cards) and not self.running)

    def _lock_inputs(self, locked: bool) -> None:
        for widget in (self.source, self.device_root, self.computer_root, self.browse, self.load, self.shared, self.full, self.grid):
            widget.setEnabled(not locked)
        self.load.setText("加载平台")

    def begin_conversion(self) -> None:
        self._queue = list(self.grid.selected())
        self._planned = sum(item.roms if self.full.isChecked() else max(0, item.roms - item.existing) for item in self._queue)
        self._processed = 0
        if not self._planned:
            self.feedback.finish("所选平台暂无新增入口（示例）。需要重新处理时，可启用“全量替换”。")
            return
        self.running = True
        self._lock_inputs(True)
        self.feedback.update_progress("正在进行示例转换…", 0)
        self.update_counts()
        self.timer.start()

    def _convert_next(self) -> None:
        item = self._queue.pop(0)
        count = item.roms if self.full.isChecked() else max(0, item.roms - item.existing)
        self._processed += count
        item.existing = item.roms
        self._history[(self.source_key(), item.id)] = item.existing
        for card in self.grid.cards:
            if card.item.id == item.id:
                card.update_details()
        self.feedback.update_progress(f"示例转换：{item.name} · 已完成 {self._processed}/{self._planned} 个入口", int(100 * self._processed / self._planned))
        if not self._queue:
            self.timer.stop()
            self.running = False
            self._lock_inputs(False)
            self.feedback.finish(f"示例转换完成：处理 {self._processed} 个入口。未生成文件、修改 metadata 或连接设备。")
        self.update_counts()

    def shutdown(self) -> None:
        self.cancel_operation()
        for worker in tuple(self._workers):
            worker.wait()
