"""Portable workspace settings and the small, shared platform-definition editor."""

from dataclasses import replace
from pathlib import Path
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
    QMessageBox, QScrollArea, QStackedWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from qfluentwidgets import ComboBox, LineEdit, PrimaryPushButton, PushButton, SearchLineEdit, SwitchButton, TableWidget

from .appearance import DARK, LIGHT
from frontend_common.state import CARD_STYLES
from .cleanup_dialog import CleanupDialog
from .state import PlatformDefinition, UiStore, valid_component
from .widgets import caption, heading, panel


class PlatformDialog(QDialog):
    def __init__(self, definitions: list[PlatformDefinition], item: PlatformDefinition | None, parent: QWidget) -> None:
        super().__init__(parent)
        self.definitions, self.original = definitions, item
        self.result_definition: PlatformDefinition | None = None
        self.setWindowTitle("编辑平台" if item else "添加平台")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(15)
        layout.addWidget(heading(self.windowTitle(), "游戏库转换与主题适配共用这份定义"))
        form = QFormLayout()
        form.setSpacing(12)
        self.name = LineEdit()
        self.directory = LineEdit()
        self.parent_platform = ComboBox()
        self.parent_platform.addItem("无母体（基础平台）", userData="")
        blocked = {item.id} if item else set()
        while True:
            descendants = {entry.id for entry in definitions if entry.parent in blocked}
            if descendants.issubset(blocked):
                break
            blocked.update(descendants)
        for entry in definitions:
            if entry.id not in blocked:
                self.parent_platform.addItem(entry.name, userData=entry.id)
        self.mode = ComboBox()
        self.mode.addItem("沿用母体素材", userData="inherit")
        self.mode.addItem("独立分类素材", userData="separate")
        self.badge = LineEdit()
        self.badge.setPlaceholderText("可选，如 HACK、VIB、MINIS")
        for title, widget in (("显示名称", self.name), ("ROM 目录", self.directory), ("母体平台", self.parent_platform), ("主题表现", self.mode), ("角标文字", self.badge)):
            form.addRow(title, widget)
            widget.setAccessibleName(title)
        layout.addLayout(form)
        self.internal_id = caption("内部标识自动生成；新分类选择母体以继承启动配置。")
        self.internal_id.setWordWrap(True)
        layout.addWidget(self.internal_id)
        self.error = caption("")
        self.error.setObjectName("error")
        self.error.setTextColor(LIGHT["danger"], DARK["danger"])
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = PushButton("取消")
        save = PrimaryPushButton("保存")
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.save)
        self.name.returnPressed.connect(self.save)
        self.directory.returnPressed.connect(self.save)
        if item:
            self.name.setText(item.name)
            self.directory.setText(item.directory)
            self.parent_platform.setCurrentIndex(self.parent_platform.findData(item.parent))
            self.mode.setCurrentIndex(self.mode.findData(item.mode))
            self.badge.setText(item.badge)
            self.internal_id.setText("内部标识：" + item.id)
        self._last_name = self.name.text()
        self.name.textEdited.connect(self._name_changed)

    def _name_changed(self, text: str) -> None:
        if self.directory.text() == self._last_name:
            self.directory.setText(text)
        self._last_name = text

    def save(self) -> None:
        name, directory = self.name.text().strip(), self.directory.text().strip()
        if not name or not valid_component(directory):
            self.error.setText("请填写显示名称和单个 ROM 目录名，不使用路径或 Windows 非法字符。")
            return
        if self.original is None and not self.parent_platform.currentData():
            self.error.setText("请选择母体平台，新分类将继承其启动配置。")
            return
        others = [entry for entry in self.definitions if self.original is None or entry.id != self.original.id]
        if any(entry.name.casefold() == name.casefold() or entry.directory.casefold() == directory.casefold() for entry in others):
            self.error.setText("显示名称或 ROM 目录已经存在。")
            return
        if self.original:
            identifier = self.original.id
        else:
            base = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "platform"
            identifier = base
            suffix = 2
            while any(entry.id == identifier for entry in others):
                identifier = f"{base}-{suffix}"
                suffix += 1
        self.result_definition = PlatformDefinition(identifier, name, directory, self.parent_platform.currentData(), self.mode.currentData(), self.badge.text().strip())
        self.accept()


class PlatformsPage(QWidget):
    changed = Signal()
    back = Signal()

    def __init__(self, store: UiStore) -> None:
        super().__init__()
        self.store = store
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 19, 24, 16)
        layout.setSpacing(12)
        breadcrumb = PushButton("← 设置")
        breadcrumb.setFixedWidth(90)
        breadcrumb.clicked.connect(self.back)
        layout.addWidget(breadcrumb)
        row = QHBoxLayout()
        row.addWidget(heading("平台管理", "维护平台分类、母体与主题素材规则"), 1)
        add = PrimaryPushButton("添加平台")
        add.clicked.connect(lambda: self.edit(None))
        row.addWidget(add)
        layout.addLayout(row)
        search_row = QHBoxLayout()
        self.search = SearchLineEdit()
        self.search.setPlaceholderText("搜索名称或 ROM 目录")
        self.search.setMinimumWidth(260)
        self.search.setMaximumWidth(310)
        self.search.setAccessibleName("搜索平台")
        self.search.textChanged.connect(self.render)
        search_row.addWidget(self.search)
        search_row.addStretch(1)
        self.counts = caption("")
        search_row.addWidget(self.counts)
        layout.addLayout(search_row)
        self.table = TableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["名称", "ROM 目录", "母体", "主题表现", "操作"])
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(False)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        for column in (0, 1):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        for column, width in ((2, 110), (3, 135), (4, 150)):
            self.table.setColumnWidth(column, width)
        layout.addWidget(self.table, 1)
        self.note = caption("删除只移除平台定义，保留 ROM、设备配置和已生成主题。完整系统配置基线始终保留。" + "\n" + "\n".join(store.catalog_notices))
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.render()

    def render(self, *_args) -> None:
        query = self.search.text().strip().casefold()
        rows = [entry for entry in self.store.definitions if query in entry.name.casefold() or query in entry.directory.casefold()]
        names = {entry.id: entry.name for entry in self.store.definitions}
        self.table.setRowCount(len(rows))
        self.counts.setText(f"显示 {len(rows)}/{len(self.store.definitions)} 个平台")
        self.note.setToolTip("\n".join(self.store.catalog_notices))
        for row, entry in enumerate(rows):
            mode = "独立分类" if entry.mode == "separate" else "沿用母体"
            values = (entry.name, entry.directory, names.get(entry.parent, "—"), mode + (f" · {entry.badge}" if entry.badge else ""))
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip("内部标识：" + entry.id if column == 0 else value)
                self.table.setItem(row, column, item)
            actions = QWidget()
            buttons = QHBoxLayout(actions)
            buttons.setContentsMargins(2, 4, 2, 4)
            buttons.setSpacing(5)
            edit = PushButton("编辑")
            delete = PushButton("删除")
            edit.setAccessibleName("编辑 " + entry.name)
            delete.setAccessibleName("删除 " + entry.name)
            edit.clicked.connect(lambda _checked=False, entry=entry: self.edit(entry))
            delete.clicked.connect(lambda _checked=False, entry=entry: self.delete(entry))
            buttons.addWidget(edit)
            buttons.addWidget(delete)
            self.table.setCellWidget(row, 4, actions)
            self.table.setRowHeight(row, 48)

    def _save(self, definitions: list[PlatformDefinition]) -> bool:
        try:
            self.store.save_definitions(definitions)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "无法保存平台配置", str(exc))
            return False
        self.render()
        self.changed.emit()
        return True

    def edit(self, item: PlatformDefinition | None) -> None:
        dialog = PlatformDialog(self.store.definitions, item, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = dialog.result_definition
        if result is None:
            return
        definitions = [replace(entry) for entry in self.store.definitions]
        if item is None:
            definitions.append(result)
        else:
            definitions = [result if entry.id == item.id else entry for entry in definitions]
        self._save(definitions)

    def delete(self, item: PlatformDefinition) -> None:
        children = [entry.name for entry in self.store.definitions if entry.parent == item.id]
        if children:
            QMessageBox.information(self, "平台仍被引用", "请先修改这些平台的母体：\n" + "、".join(children))
            return
        # Only the local definition is removed; no device or media operations.
        self._save([entry for entry in self.store.definitions if entry.id != item.id])


class SettingsPage(QWidget):
    workspace_changed = Signal()
    definitions_changed = Signal()
    theme_changed = Signal(str)
    card_style_changed = Signal(str)
    workspace_cleaned = Signal()

    def __init__(self, store: UiStore, hub) -> None:
        super().__init__()
        self.store, self.hub = store, hub
        self.setObjectName("settingsPage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        general = QWidget()
        content = QVBoxLayout(general)
        content.setContentsMargins(24, 19, 24, 16)
        content.setSpacing(14)
        content.addWidget(heading("设置", "整个软件共用一个工作目录"))
        appearance, appearance_layout = panel()
        appearance_row = QHBoxLayout()
        appearance_row.addWidget(heading("外观", "亮色与暗色即时切换，自动记住你的选择", section=True), 1)
        self.theme_switch = SwitchButton()
        self.theme_switch.setOnText("暗色")
        self.theme_switch.setOffText("亮色")
        self.theme_switch.setChecked(store.theme == "dark")
        self.theme_switch.setAccessibleName("暗色模式")
        appearance_row.addWidget(self.theme_switch)
        appearance_layout.addLayout(appearance_row)
        art_row = QHBoxLayout()
        art_row.addWidget(caption("平台卡片风格"), 1)
        self.card_style = ComboBox()
        for key, title in CARD_STYLES.items():
            self.card_style.addItem(title, userData=key)
        self.card_style.setCurrentIndex(list(CARD_STYLES).index(store.card_style))
        self.card_style.currentIndexChanged.connect(self._change_card_style)
        art_row.addWidget(self.card_style)
        appearance_layout.addLayout(art_row)
        content.addWidget(appearance)
        frame, controls = panel()
        controls.addWidget(heading("工作目录", "原版主题、导出结果、配置和临时文件统一管理", section=True))
        row = QHBoxLayout()
        self.workspace = LineEdit()
        self.workspace.setText(str(store.workspace))
        self.workspace.setAccessibleName("软件工作目录")
        row.addWidget(self.workspace, 1)
        browse = PushButton("浏览…")
        save = PrimaryPushButton("保存")
        row.addWidget(browse)
        row.addWidget(save)
        controls.addLayout(row)
        details = caption("config/  ·  themes/original/  ·  themes/exported/  ·  library/  ·  devices/  ·  logs/  ·  temp/")
        details.setWordWrap(True)
        controls.addWidget(details)
        note = caption("基础设置保存在程序同级的 settings.json；更换工作目录不会搬移旧目录的数据。")
        note.setWordWrap(True)
        controls.addWidget(note)
        content.addWidget(frame)
        frame, controls = panel()
        row = QHBoxLayout()
        row.addWidget(heading("平台定义", "统一管理 GBA hack、GBA vib、PSP Minis 等分类", section=True), 1)
        manage = PushButton("管理平台 →")
        row.addWidget(manage)
        controls.addLayout(row)
        content.addWidget(frame)
        clean_frame, clean_controls = panel()
        clean_row = QHBoxLayout()
        clean_row.addWidget(heading("工作目录清理", "预览并手动清理临时文件、备份与恢复资料、历史日志", section=True), 1)
        clean_button = PushButton("清理工作目录…")
        clean_button.clicked.connect(self._cleanup)
        clean_row.addWidget(clean_button)
        clean_controls.addLayout(clean_row)
        content.addWidget(clean_frame)
        self.feedback = caption("\n".join(store.catalog_notices))
        self.feedback.setWordWrap(True)
        content.addWidget(self.feedback)
        content.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(general)
        self.stack.addWidget(scroll)
        self.platforms = PlatformsPage(store)
        self.stack.addWidget(self.platforms)
        self.platforms.back.connect(lambda: self.stack.setCurrentIndex(0))
        self.platforms.changed.connect(self.definitions_changed)
        manage.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        browse.clicked.connect(self._browse)
        save.clicked.connect(self._save)
        self.theme_switch.checkedChanged.connect(self._change_theme)

    def _cleanup(self):
        dialog = CleanupDialog(self.store, self.hub, self)
        dialog.exec()
        if dialog.did_clean:
            self.workspace_cleaned.emit()
        dialog.deleteLater()

    def _change_card_style(self, _index):
        try:
            self.store.save_card_style(self.card_style.currentData())
        except (OSError, ValueError) as exc:
            self.card_style.blockSignals(True)
            self.card_style.setCurrentIndex(list(CARD_STYLES).index(self.store.card_style))
            self.card_style.blockSignals(False)
            self.feedback.setText("卡片风格保存失败：" + str(exc))
            return
        self.card_style_changed.emit(self.store.card_style)

    def _change_theme(self, checked: bool) -> None:
        mode = "dark" if checked else "light"
        try:
            self.store.save_theme(mode)
        except (OSError, ValueError) as exc:
            self.theme_switch.blockSignals(True)
            self.theme_switch.setChecked(self.store.theme == "dark")
            self.theme_switch.blockSignals(False)
            self.feedback.setText("外观设置保存失败：" + str(exc))
            return
        self.theme_changed.emit(mode)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择软件工作目录", str(self.store.workspace))
        if path:
            self.workspace.setText(path)

    def _save(self) -> None:
        path = Path(self.workspace.text().strip())
        if not self.workspace.text().strip() or not path.is_absolute():
            self.feedback.setText("请选择或填写绝对路径。")
            return
        try:
            self.store.change_workspace(path)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.feedback.setText("保存失败：" + str(exc))
            return
        self.workspace.setText(str(self.store.workspace))
        self.feedback.setText("已保存工作目录，基础设置位于：" + str(self.store.settings_file))
        self.platforms.render()
        self.workspace_changed.emit()
