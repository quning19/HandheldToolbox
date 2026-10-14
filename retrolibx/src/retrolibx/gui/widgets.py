"""Shared native widgets and a compact platform-art grid."""

import math
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)
from qfluentwidgets import BodyLabel, CaptionLabel, ProgressBar, PushButton

from .state import PlatformPreview


def caption(text: str, parent: QWidget | None = None) -> CaptionLabel:
    label = CaptionLabel(text, parent)
    label.setTextColor("#647083", "#adb7c6")
    label.setObjectName("muted")
    return label


def heading(title: str, subtitle: str) -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(3)
    label = QLabel(title)
    label.setObjectName("pageTitle")
    layout.addWidget(label)
    layout.addWidget(caption(subtitle))
    return widget


def panel() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("surface")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(10)
    return frame, layout


class TaskFeedback(QFrame):
    cancelled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("feedback")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(5)
        row = QHBoxLayout()
        self.message = BodyLabel()
        self.message.setWordWrap(True)
        row.addWidget(self.message, 1)
        self.stop = PushButton("取消")
        self.stop.clicked.connect(self.cancelled)
        row.addWidget(self.stop)
        layout.addLayout(row)
        self.bar = ProgressBar()
        layout.addWidget(self.bar)
        self.hide()

    def update_progress(self, text: str, value: int, cancellable: bool = True) -> None:
        self.message.setText(text)
        self.bar.setValue(value)
        self.bar.show()
        self.stop.setVisible(cancellable)
        self.show()

    def finish(self, text: str) -> None:
        self.message.setText(text)
        self.bar.hide()
        self.stop.hide()
        self.show()


class PlatformCard(QPushButton):
    def __init__(self, item: PlatformPreview, parent: QWidget) -> None:
        super().__init__(parent)
        self.item = item
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.art = QPixmap(str(Path(__file__).parent / "assets/platforms" / (item.art + ".webp")))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.update_details()

    def update_details(self) -> None:
        item = self.item
        self.setAccessibleName(f"{item.name}，{item.roms} 个 ROM，{item.covers} 个封面")
        self.setToolTip(
            f"{item.name}\nROM：{item.roms}，封面：{item.covers}\n"
            f"新增：{max(0, item.roms - item.existing)}（示例）"
            + (f"\nmetadata 中另有 {item.missing_references} 个缺失引用，未计入 ROM" if item.missing_references else "")
        )
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(1, 1, self.width() - 2, self.height() - 2)
        shape = QPainterPath()
        shape.addRoundedRect(bounds, 8, 8)
        painter.setClipPath(shape)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        art_height = self.height() - 49
        painter.save()
        painter.setClipRect(0, 0, self.width(), art_height, Qt.ClipOperation.IntersectClip)
        if self.art.isNull():
            painter.fillRect(0, 0, self.width(), art_height, QColor("#385873"))
        else:
            scaled = self.art.scaled(
                self.width(), art_height, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap((self.width() - scaled.width()) // 2, (art_height - scaled.height()) // 2, scaled)
        painter.restore()
        painter.fillRect(0, 0, self.width(), art_height, QColor(0, 0, 0, 28))
        font = QFont("Segoe UI", 20, QFont.Weight.Bold)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        text = self.item.name
        while metrics.horizontalAdvance(text) > self.width() - 24 and font.pointSize() > 12:
            font.setPointSize(font.pointSize() - 1)
            painter.setFont(font)
            metrics = painter.fontMetrics()
        path = QPainterPath()
        path.addText((self.width() - metrics.horizontalAdvance(text)) / 2, art_height / 2 + metrics.ascent() / 3, font, text)
        painter.setPen(QPen(QColor(0, 0, 0, 210), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.fillPath(path, QColor("white"))
        tick = QRectF(self.width() - 29, 10, 18, 18)
        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.setBrush(QColor("#0968bb") if self.isChecked() else QColor(0, 0, 0, 95))
        painter.drawRoundedRect(tick, 4, 4)
        if self.isChecked():
            painter.setPen(QPen(QColor("white"), 2))
            painter.drawLine(int(tick.left() + 4), int(tick.top() + 9), int(tick.left() + 8), int(tick.top() + 13))
            painter.drawLine(int(tick.left() + 8), int(tick.top() + 13), int(tick.left() + 14), int(tick.top() + 5))
        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QColor("#242a32"))
        painter.drawText(11, art_height + 20, f"{self.item.roms} ROM")
        text = f"封面 {self.item.covers}/{self.item.roms}"
        painter.setPen(QColor("#647083"))
        painter.drawText(self.width() - painter.fontMetrics().horizontalAdvance(text) - 11, art_height + 20, text)
        text = f"新增 {max(0, self.item.roms - self.item.existing)}" if self.item.roms > self.item.existing else "已收录"
        painter.drawText(11, art_height + 39, text)
        painter.setClipping(False)
        painter.setPen(QPen(QColor("#0968bb") if self.isChecked() or self.hasFocus() else QColor("#dce1e8"), 2 if self.isChecked() else 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(bounds, 8, 8)
        painter.end()


class PlatformGrid(QWidget):
    selection_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.cards: list[PlatformCard] = []
        self.setMinimumHeight(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    def clear(self) -> None:
        for card in self.cards:
            card.hide()
            card.deleteLater()
        self.cards.clear()
        self.setMinimumHeight(1)

    def append(self, item: PlatformPreview) -> None:
        card = PlatformCard(item, self)
        card.toggled.connect(self.selection_changed)
        self.cards.append(card)
        card.show()
        self.reflow()

    def selected(self) -> list[PlatformPreview]:
        return [card.item for card in self.cards if card.isChecked()]

    def select_all(self, checked: bool) -> None:
        for card in self.cards:
            card.setChecked(checked)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.reflow()

    def reflow(self) -> None:
        gap = 10
        columns = max(1, (self.width() + gap) // 180)
        width = max(1, (self.width() - (columns - 1) * gap) // columns)
        height = int(width * .84) + 49
        for index, card in enumerate(self.cards):
            card.setGeometry((index % columns) * (width + gap), (index // columns) * (height + gap), width, height)
        self.setMinimumHeight(max(1, math.ceil(len(self.cards) / columns) * (height + gap) - gap))
