"""Shared native widgets and a compact platform-art grid."""

import math
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)
from qfluentwidgets import CaptionLabel, ProgressBar, PushButton

from retrolibx.application.desktop import PlatformInfo
from .appearance import DARK, LIGHT, colors, ui_font


class NavigationButton(QToolButton):
    """Show a focus outline for keyboard navigation, independently of selection."""

    def __init__(self) -> None:
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setProperty("keyboardFocus", False)

    def _set_keyboard_focus(self, visible: bool) -> None:
        if self.property("keyboardFocus") == visible:
            return
        self.setProperty("keyboardFocus", visible)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self._set_keyboard_focus(event.reason() in (
            Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason,
            Qt.FocusReason.ShortcutFocusReason,
        ))

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._set_keyboard_focus(False)

    def mousePressEvent(self, event) -> None:
        self._set_keyboard_focus(False)
        super().mousePressEvent(event)


def caption(text: str, parent: QWidget | None = None, *, tone: str = "muted") -> CaptionLabel:
    label = CaptionLabel(text, parent)
    label.setFont(ui_font(13))
    label.setTextColor(LIGHT[tone], DARK[tone])
    label.setObjectName("muted")
    return label


class ElidedCaption(CaptionLabel):
    """A single-line path hint that never forces its toolbar wider."""

    def __init__(self) -> None:
        self._full_text = ""
        super().__init__()
        self.setFont(ui_font(13))
        self.setTextColor(LIGHT["muted"], DARK["muted"])
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)

    def setText(self, text: str) -> None:
        self._full_text = text
        self.setToolTip(text)
        self._fit()

    def _fit(self) -> None:
        super().setText(self.fontMetrics().elidedText(self._full_text, Qt.TextElideMode.ElideMiddle, max(0, self.contentsRect().width())))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit()


def heading(title: str, subtitle: str, *, section: bool = False) -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(5)
    label = QLabel(title)
    label.setObjectName("sectionTitle" if section else "pageTitle")
    layout.addWidget(label)
    description = caption(subtitle)
    description.setWordWrap(True)
    layout.addWidget(description)
    return widget


def panel() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("surface")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(12)
    return frame, layout


def status_badge(text: str, tone: str) -> QWidget:
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(7, 0, 7, 0)
    label = QLabel(text)
    label.setObjectName("statusBadge")
    label.setProperty("tone", tone)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(label, 0, Qt.AlignmentFlag.AlignCenter)
    return widget


class TaskFeedback(QFrame):
    """A fixed-height footer whose reserved space survives every task state."""

    cancelled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("feedback")
        self.setFixedHeight(72)
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        policy.setRetainSizeWhenHidden(True)
        self.setSizePolicy(policy)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)
        row = QHBoxLayout()
        self.message = ElidedCaption()
        self.message.setFont(ui_font(14))
        self.message.setTextColor(LIGHT["ink"], DARK["ink"])
        row.addWidget(self.message, 1)
        self.stop = PushButton("取消")
        self.stop.setFixedHeight(32)
        stop_policy = self.stop.sizePolicy()
        stop_policy.setRetainSizeWhenHidden(True)
        self.stop.setSizePolicy(stop_policy)
        self.stop.clicked.connect(self.cancelled)
        row.addWidget(self.stop)
        layout.addLayout(row)
        self.bar = ProgressBar()
        self.bar.setFixedHeight(4)
        bar_policy = self.bar.sizePolicy()
        bar_policy.setRetainSizeWhenHidden(True)
        self.bar.setSizePolicy(bar_policy)
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
    def __init__(self, item: PlatformInfo, parent: QWidget) -> None:
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
            f"新增：{max(0, item.roms - item.existing)}"
            + (f"\nmetadata 中另有 {item.missing_references} 个缺失引用，未计入 ROM" if item.missing_references else "")
            + (f"\n{item.unlinked} 个 ROM 未关联资料，不会自动生成游戏信息" if item.unlinked else "")
            + ("\n无法转换：" + item.error if item.error else "")
        )
        self.update()

    def paintEvent(self, event) -> None:
        c = colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(1, 1, self.width() - 2, self.height() - 2)
        shape = QPainterPath()
        shape.addRoundedRect(bounds, 10, 10)
        painter.setClipPath(shape)
        painter.fillRect(self.rect(), QColor(c["accent_soft"] if self.isChecked() else c["surface"]))
        art_height = self.height() - 56
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
        font = ui_font(24, QFont.Weight.Bold)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        text = self.item.name
        while metrics.horizontalAdvance(text) > self.width() - 24 and font.pixelSize() > 15:
            font.setPixelSize(font.pixelSize() - 1)
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
        painter.setBrush(QColor(c["accent"]) if self.isChecked() else QColor(0, 0, 0, 95))
        painter.drawRoundedRect(tick, 4, 4)
        if self.isChecked():
            painter.setPen(QPen(QColor(DARK["canvas"] if c is DARK else "#FFFFFF"), 2))
            painter.drawLine(int(tick.left() + 4), int(tick.top() + 9), int(tick.left() + 8), int(tick.top() + 13))
            painter.drawLine(int(tick.left() + 8), int(tick.top() + 13), int(tick.left() + 14), int(tick.top() + 5))
        painter.setFont(ui_font(13, QFont.Weight.DemiBold))
        painter.setPen(QColor(c["ink"]))
        painter.drawText(11, art_height + 22, f"{self.item.roms} ROM")
        text = f"封面 {self.item.covers}/{self.item.roms}"
        painter.setFont(ui_font(12))
        painter.setPen(QColor(c["warning"] if self.item.covers < self.item.roms else c["muted"]))
        painter.drawText(self.width() - painter.fontMetrics().horizontalAdvance(text) - 11, art_height + 22, text)
        added = max(0, self.item.roms - self.item.existing)
        if self.item.error:
            painter.setPen(QColor(c["danger"]))
            painter.drawText(11, art_height + 44, "需要处理 · 悬停查看")
        elif added:
            text = f"新增 {added}"
            badge = QRectF(10, art_height + 31, painter.fontMetrics().horizontalAdvance(text) + 14, 18)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(c["success_soft"]))
            painter.drawRoundedRect(badge, 4, 4)
            painter.setPen(QColor(c["success"]))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, text)
        else:
            painter.setPen(QColor(c["muted"]))
            painter.drawText(11, art_height + 44, "已收录")
        painter.setClipping(False)
        active = self.isChecked() or self.hasFocus() or self.underMouse()
        painter.setPen(QPen(QColor(c["accent"] if active else c["border"]), 2 if active else 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(bounds, 10, 10)
        painter.end()

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self.update()


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

    def append(self, item: PlatformInfo) -> None:
        card = PlatformCard(item, self)
        card.toggled.connect(self.selection_changed)
        self.cards.append(card)
        card.show()
        self.reflow()

    def selected(self) -> list[PlatformInfo]:
        return [card.item for card in self.cards if card.isChecked()]

    def select_all(self, checked: bool) -> None:
        for card in self.cards:
            card.setChecked(checked)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.reflow()

    def reflow(self) -> None:
        gap = 12
        columns = max(1, (self.width() + gap) // 180)
        width = max(1, (self.width() - (columns - 1) * gap) // columns)
        height = int(width * .84) + 56
        for index, card in enumerate(self.cards):
            card.setGeometry((index % columns) * (width + gap), (index // columns) * (height + gap), width, height)
        self.setMinimumHeight(max(1, math.ceil(len(self.cards) / columns) * (height + gap) - gap))
