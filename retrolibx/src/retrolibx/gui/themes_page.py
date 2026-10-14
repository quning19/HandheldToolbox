"""Original/converted/device theme states with explicitly simulated operations."""

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QTableWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import PrimaryPushButton, PushButton, TableWidget

from .state import UiStore, example_themes
from .widgets import TaskFeedback, caption, heading, panel


class ThemesPage(QWidget):
    def __init__(self, store: UiStore) -> None:
        super().__init__()
        self.store = store
        self.themes = example_themes()
        self.selected: set[str] = set()
        self.running = False
        self._queue = []
        self._completed = 0
        self.setObjectName("themesPage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 19, 24, 16)
        layout.setSpacing(12)
        layout.addWidget(heading("主题适配", "同步原版 → 转换主题 → 上传到设备"))
        toolbar, controls = panel()
        self.paths = caption("")
        self.paths.setWordWrap(True)
        controls.addWidget(self.paths)
        row = QHBoxLayout()
        self.sync = PushButton("同步原版")
        self.convert = PrimaryPushButton("转换主题")
        self.upload = PushButton("上传主题")
        self.refresh = PushButton("刷新设备主题")
        for button in (self.sync, self.convert, self.upload):
            row.addWidget(button)
        row.addStretch(1)
        row.addWidget(self.refresh)
        controls.addLayout(row)
        layout.addWidget(toolbar)
        selection = QHBoxLayout()
        self.counts = caption("")
        selection.addWidget(self.counts, 1)
        all_button = PushButton("全选")
        none_button = PushButton("清空选择")
        self.selection_buttons = (all_button, none_button)
        selection.addWidget(all_button)
        selection.addWidget(none_button)
        all_button.clicked.connect(lambda: self.select_all(True))
        none_button.clicked.connect(lambda: self.select_all(False))
        layout.addLayout(selection)
        self.table = TableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["选择", "主题", "本地原版", "转换结果", "设备主题"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setAlternatingRowColors(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column, width in ((0, 54), (2, 118), (3, 130), (4, 118)):
            self.table.setColumnWidth(column, width)
        self.table.itemChanged.connect(self._selection_changed)
        layout.addWidget(self.table, 1)
        note = caption("设备“已存在”仅表示主题目录存在，不代表与本地最新结果一致。此页状态与操作均为示例。")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.feedback = TaskFeedback()
        self.feedback.cancelled.connect(self.cancel_operation)
        layout.addWidget(self.feedback)
        self.timer = QTimer(self)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self._next)
        self.sync.clicked.connect(lambda: self.begin("sync"))
        self.convert.clicked.connect(lambda: self.begin("convert"))
        self.upload.clicked.connect(lambda: self.begin("upload"))
        self.refresh.clicked.connect(lambda: self.begin("refresh"))
        self.update_paths()
        self.render()

    def update_paths(self) -> None:
        self.paths.setText(f"工作目录：{self.store.workspace}  ·  原版 /themes/original  ·  导出 /themes/exported")
        self.paths.setToolTip(f"上传目标：内置存储 ES-DE/themes（示例）\n平台分类：{len(self.store.definitions)} 个")

    def render(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.themes))
        for row, theme in enumerate(self.themes):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Checked if theme.name in self.selected else Qt.CheckState.Unchecked)
            check.setData(Qt.ItemDataRole.UserRole, theme.name)
            check.setToolTip("选择 " + theme.name)
            self.table.setItem(row, 0, check)
            values = (theme.name, "已同步" if theme.original else "未同步", "可上传" if theme.converted else "未转换", "未检查" if theme.device is None else ("已存在" if theme.device else "未发现"))
            for column, value in enumerate(values, 1):
                self.table.setItem(row, column, QTableWidgetItem(value))
            self.table.setRowHeight(row, 53)
        self.table.blockSignals(False)
        self.update_actions()

    def _selection_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self.selected.add(name)
        else:
            self.selected.discard(name)
        self.update_actions()

    def select_all(self, checked: bool) -> None:
        self.selected = {theme.name for theme in self.themes} if checked else set()
        self.render()

    def update_actions(self) -> None:
        selected = [theme for theme in self.themes if theme.name in self.selected]
        self.counts.setText(f"主题 {len(self.themes)} · 已选 {len(selected)} · 可上传 {sum(theme.converted for theme in selected)}")
        self.sync.setEnabled(bool(selected) and not self.running)
        self.convert.setEnabled(bool(selected) and all(theme.original for theme in selected) and not self.running)
        self.upload.setEnabled(bool(selected) and all(theme.converted for theme in selected) and not self.running)
        self.refresh.setEnabled(not self.running)
        self.convert.setToolTip("请先同步所有所选主题的原版。")
        self.upload.setToolTip("请先转换所有所选主题。")
        self.table.setEnabled(not self.running)
        for button in self.selection_buttons:
            button.setEnabled(not self.running)

    def begin(self, operation: str) -> None:
        self.operation = operation
        self._queue = list(self.themes) if operation == "refresh" else [theme for theme in self.themes if theme.name in self.selected]
        if not self._queue:
            return
        self._total, self._completed = len(self._queue), 0
        self.running = True
        self.feedback.update_progress("正在执行示例操作…", 0)
        self.update_actions()
        self.timer.start()

    def _next(self) -> None:
        theme = self._queue.pop(0)
        if self.operation == "sync":
            theme.original = True
        elif self.operation == "convert":
            theme.converted = True
        elif self.operation == "upload":
            theme.device = True
        elif theme.device is None:
            theme.device = theme.name in {"Canvas", "iiSU Interpreted", "PlayStation-X"}
        self._completed += 1
        names = {"sync": "同步原版", "convert": "转换主题", "upload": "上传主题", "refresh": "刷新设备主题"}
        self.feedback.update_progress(f"{names[self.operation]}（示例）：{theme.name} · {self._completed}/{self._total}", int(100 * self._completed / self._total))
        if not self._queue:
            self.timer.stop()
            self.running = False
            self.feedback.finish(f"{names[self.operation]}示例完成。未下载、生成或上传实际主题。")
            # Successful example uploads also refresh previously unknown device states.
            if self.operation == "upload":
                for entry in self.themes:
                    if entry.device is None:
                        entry.device = entry.name in {"Canvas", "iiSU Interpreted", "PlayStation-X"}
        self.render()

    def cancel_operation(self) -> None:
        self.timer.stop()
        if self.running:
            self.feedback.finish(f"已取消示例操作，已完成 {self._completed}/{self._total} 个主题。")
        self.running = False
        self.update_actions()

    def reset_workspace(self) -> None:
        self.cancel_operation()
        self.themes = example_themes()
        self.selected.clear()
        self.feedback.hide()
        self.update_paths()
        self.render()
