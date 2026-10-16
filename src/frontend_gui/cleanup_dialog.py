"""Three explicit cleanup categories, with immutable preview and per-batch choice."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QTableWidgetItem, QHeaderView, QMessageBox
from qfluentwidgets import CheckBox, PushButton, PrimaryPushButton, TableWidget
from frontend_common.cleanup import CATEGORIES, preview_cleanup, clean_workspace
from .widgets import caption, TaskFeedback


class CleanupDialog(QDialog):
    def __init__(self, store, hub, parent=None):
        super().__init__(parent)
        self.store, self.hub = store, hub
        self.items = []
        self.did_clean = False
        self.setWindowTitle("清理工作目录")
        self.resize(850, 560)
        layout = QVBoxLayout(self)
        note = caption("仅清理本地工作目录。最新备份默认不选；当前日志、设置、原版和正式输出始终保留。")
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        self.categories = {}
        for key, title in CATEGORIES.items():
            checkbox = CheckBox(title)
            checkbox.setChecked(key == "temp")
            checkbox.stateChanged.connect(self.select_categories)
            row.addWidget(checkbox)
            self.categories[key] = checkbox
        row.addStretch(1)
        self.refresh = PushButton("刷新预览")
        row.addWidget(self.refresh)
        layout.addLayout(row)
        self.table = TableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["选择", "项目", "文件数", "大小"])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column, width in ((0, 55), (2, 80), (3, 110)):
            self.table.setColumnWidth(column, width)
        self.table.itemChanged.connect(self.update_count)
        layout.addWidget(self.table, 1)
        self.retained = caption("")
        self.retained.setWordWrap(True)
        layout.addWidget(self.retained)
        row = QHBoxLayout()
        self.count = caption("")
        row.addWidget(self.count, 1)
        self.execute = PrimaryPushButton("清理所选")
        self.close_button = PushButton("关闭")
        row.addWidget(self.execute)
        row.addWidget(self.close_button)
        layout.addLayout(row)
        self.feedback = TaskFeedback()
        layout.addWidget(self.feedback)
        self.refresh.clicked.connect(self.load)
        self.execute.clicked.connect(self.clean)
        self.close_button.clicked.connect(self.reject)
        self.hub.busy_changed.connect(self.set_busy)
        QTimer.singleShot(0, self.load)

    def set_busy(self, busy):
        self.refresh.setEnabled(not busy)
        self.table.setEnabled(not busy)
        self.close_button.setEnabled(not busy)
        for checkbox in self.categories.values():
            checkbox.setEnabled(not busy)
        self.update_count()

    def load(self):
        def complete(result):
            self.items, retained = result
            self.table.blockSignals(True)
            self.table.setRowCount(len(self.items))
            for row, item in enumerate(self.items):
                check = QTableWidgetItem()
                check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                check.setCheckState(Qt.CheckState.Unchecked)
                self.table.setItem(row, 0, check)
                label = item.relative + ("（最新备份）" if item.latest else "")
                for column, text in enumerate((label, str(item.files), f"{item.bytes / 1048576:.2f} MB"), 1):
                    cell = QTableWidgetItem(text)
                    cell.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    cell.setToolTip("\n".join(item.details))
                    self.table.setItem(row, column, cell)
            self.table.blockSignals(False)
            self.retained.setText(f"另有 {len(retained)} 项因用途未登记或路径限制保留。" if retained else "")
            self.retained.setToolTip("\n".join(retained))
            self.select_categories()
            self.feedback.finish("清理预览已更新；悬停项目可查看文件明细。")
        def operation(worker):
            worker.progress.emit("读取清理预览…", 0, False)
            return preview_cleanup(self.store.workspace)
        self.hub.start(operation, self.feedback, complete)

    def select_categories(self, *_):
        for row, item in enumerate(self.items):
            checked = self.categories[item.category].isChecked() and not item.latest
            self.table.item(row, 0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.update_count()

    def selected(self):
        return [item for row, item in enumerate(self.items)
                if self.table.item(row, 0).checkState() == Qt.CheckState.Checked]

    def update_count(self, *_):
        selected = self.selected()
        self.count.setText(f"已选 {len(selected)} 项 · {sum(item.bytes for item in selected) / 1048576:.2f} MB")
        self.execute.setEnabled(bool(selected) and not self.hub.busy)

    def clean(self):
        selected = self.selected()
        if not selected:
            return
        message = f"永久删除所选 {len(selected)} 项本地文件？\n" + "\n".join(item.relative for item in selected)
        if QMessageBox.question(self, "确认清理", message) != QMessageBox.StandardButton.Yes:
            return
        def complete(result):
            self.did_clean = True
            self.feedback.finish(result["message"] + " 请刷新预览。")
            self.items = []
            self.table.setRowCount(0)
            self.update_count()
        def operation(worker):
            worker.progress.emit("正在清理已确认的项目…", 0, False)
            return clean_workspace(self.store.workspace, selected, locked=True)
        self.hub.start(operation, self.feedback, complete)

    def reject(self):
        if not self.hub.busy:
            super().reject()
