"""Managed themes backed by local adaptation and ADB services."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QTableWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import PrimaryPushButton, PushButton, TableWidget

from retrolibx.application.themes import local_themes, run_themes
from .appearance import ui_font
from .state import UiStore
from .tasks import TaskHub
from .widgets import ElidedCaption, TaskFeedback, caption, heading, panel, status_badge


class ThemesPage(QWidget):
    def __init__(self, store: UiStore, hub: TaskHub) -> None:
        super().__init__()
        self.store = store
        self.hub = hub
        self.device = None
        self.themes = local_themes(store.workspace, store.definitions)
        self.selected: set[str] = set()
        self.setObjectName("themesPage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 19, 24, 16)
        layout.setSpacing(12)
        layout.addWidget(heading("主题适配", "同步原版 → 转换主题 → 上传到设备"))
        toolbar, controls = panel()
        self.paths = ElidedCaption()
        controls.addWidget(self.paths)
        row = QHBoxLayout()
        self.sync = PushButton("同步原版")
        self.convert = PrimaryPushButton("转换主题")
        self.upload = PushButton("上传主题")
        self.refresh = PushButton("刷新设备主题")
        for button in (self.sync, self.convert, self.upload, self.refresh):
            button.setMinimumHeight(36)
        for button in (self.sync, self.convert, self.upload):
            row.addWidget(button)
        row.addStretch(1)
        row.addWidget(self.refresh)
        controls.addLayout(row)
        layout.addWidget(toolbar)
        selection = QHBoxLayout()
        self.counts = caption("", tone="accent_ink")
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
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 52)
        for column in range(1, 5):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
            if column > 1:
                self.table.horizontalHeaderItem(column).setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.itemChanged.connect(self._selection_changed)
        layout.addWidget(self.table, 1)
        note = caption("设备“已存在”仅表示主题目录存在，不代表与本地最新结果一致。原版与结果由软件工作目录统一管理。")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.feedback = TaskFeedback()
        self.feedback.cancelled.connect(self.hub.cancel)
        layout.addWidget(self.feedback)
        self.sync.clicked.connect(lambda: self.begin("sync"))
        self.convert.clicked.connect(lambda: self.begin("convert"))
        self.upload.clicked.connect(lambda: self.begin("upload"))
        self.refresh.clicked.connect(lambda: self.begin("refresh"))
        self.hub.busy_changed.connect(self.update_actions)
        self.update_paths()
        self.render()


    def update_paths(self):
        target = self.device.esde_root + "/themes" if self.device else "等待连接设备"
        self.paths.setText(f"本地工作区 · {self.store.workspace.name}     上传到 {target}")
        self.paths.setToolTip(f"工作目录：{self.store.workspace}\n原版：themes/original\n导出：themes/exported\n上传目标：{target}")

    def set_device(self, device):
        self.device = device
        for theme in self.themes:
            theme.device = None
        self.update_paths()
        self.render()

    def render(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.themes))
        for row, theme in enumerate(self.themes):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Checked if theme.id in self.selected else Qt.CheckState.Unchecked)
            check.setData(Qt.ItemDataRole.UserRole, theme.id)
            check.setToolTip("选择 " + theme.name)
            self.table.setItem(row, 0, check)
            values = (theme.name, "已同步" if theme.original else "未同步", "可上传" if theme.converted else "未转换",
                      "未检查" if theme.device is None else "已存在" if theme.device else "未发现")
            for column, value in enumerate(values, 1):
                item = QTableWidgetItem(value if column == 1 else "")
                item.setToolTip(value)
                item.setData(Qt.ItemDataRole.AccessibleTextRole, value)
                if column == 1:
                    item.setFont(ui_font(14, QFont.Weight.DemiBold))
                self.table.setItem(row, column, item)
                if column > 1:
                    tone = {"已同步": "success", "可上传": "accent", "未转换": "warning", "已存在": "success"}.get(value, "muted")
                    self.table.setCellWidget(row, column, status_badge(value, tone))
            self.table.setRowHeight(row, 56)
        self.table.blockSignals(False)
        self.update_actions()

    def _selection_changed(self, item):
        if item.column() != 0:
            return
        identity = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self.selected.add(identity)
        else:
            self.selected.discard(identity)
        self.update_actions()

    def select_all(self, checked):
        self.selected = {theme.id for theme in self.themes} if checked else set()
        self.render()

    def update_actions(self, *_args):
        selected = [theme for theme in self.themes if theme.id in self.selected]
        busy = self.hub.busy
        self.counts.setText(f"主题 {len(self.themes)} · 已选 {len(selected)} · 可上传 {sum(theme.converted for theme in selected)}")
        self.sync.setEnabled(bool(selected) and self.device is not None and not busy)
        self.convert.setEnabled(bool(selected) and all(theme.original for theme in selected) and not busy)
        self.upload.setEnabled(bool(selected) and all(theme.converted for theme in selected) and self.device is not None and not busy)
        self.refresh.setEnabled(not busy)
        self.convert.setToolTip("请先同步所选主题的原版，或将原版主题放入工作目录的 themes/original。")
        self.upload.setToolTip("请先连接设备并转换所有所选主题。")
        self.table.setEnabled(not busy)
        for button in self.selection_buttons:
            button.setEnabled(not busy)

    def begin(self, operation):
        if self.hub.busy:
            return
        workspace, definitions = self.store.workspace, list(self.store.definitions)
        identities = [theme.id for theme in self.themes if theme.id in self.selected]
        device = self.device
        if operation != "refresh" and not identities:
            return
        # On read failure keep device status unknown instead of reporting absence.
        if operation in {"refresh", "upload"}:
            for theme in self.themes:
                theme.device = None
            self.render()

        def complete(result):
            self.themes = result if isinstance(result, list) else result["themes"]
            self.render()
            self.feedback.finish("主题列表已刷新。" if isinstance(result, list) else result["message"])

        def failed(_message):
            self.themes = local_themes(workspace, definitions)
            self.render()

        self.hub.start(lambda worker: run_themes(operation, workspace, definitions, identities, device,
                                                worker.isInterruptionRequested, worker.progress.emit),
                       self.feedback, complete, on_error=failed)

    def cancel_operation(self):
        self.hub.cancel()

    def reset_workspace(self):
        self.themes = local_themes(self.store.workspace, self.store.definitions)
        self.selected.clear()
        self.feedback.hide()
        self.update_paths()
        self.render()
