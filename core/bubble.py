# -*- coding: utf-8 -*-
"""台词气泡框（Phase 3）：独立置顶透明窗口，圆角气泡 + 尾巴，自动消失。

- 独立顶层窗口：不占用桌宠窗口的画布，文字可自由换行伸缩。
- WA_TransparentForMouseEvents：气泡不拦截任何鼠标操作（点击会穿透）。
- show_text(text, anchor=pet)：锚定桌宠，气泡贴在其头顶；桌宠被拖动时
  调用 reposition() 保持跟随；顶部空间不足时自动翻到身体下方（尾巴朝上）。
"""
from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QGuiApplication,
                           QPainter, QPainterPath, QPen)
from PySide6.QtWidgets import QLabel, QWidget

from core import config

_TAIL_H = 8          # 尾巴高度
_MAX_TEXT_W = 260    # 文字最大宽度（超出自动换行）
_PAD_X, _PAD_Y = 14, 10


class BubbleWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(None)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)   # 点击穿透
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._label = QLabel(self)
        self._label.setFont(QFont("Microsoft YaHei", 10))
        self._label.setStyleSheet("color: #3a3a3a;")
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setWordWrap(True)

        self._anchor = None        # 锚定的桌宠窗口
        self._tail_up = False      # 气泡在宠物下方时尾巴朝上
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    # ------------------------------------------------------------------ API
    def show_text(self, text, duration_ms=None, anchor=None):
        """显示一条台词，duration_ms 后自动消失。"""
        self._anchor = anchor
        duration = duration_ms or config.BUBBLE_DURATION_MS

        fm = QFontMetrics(self._label.font())
        rect = fm.boundingRect(0, 0, _MAX_TEXT_W, 0, Qt.TextWordWrap, text)
        label_w = min(_MAX_TEXT_W, rect.width())
        label_h = max(rect.height(), fm.height())
        self.setFixedSize(label_w + _PAD_X * 2, label_h + _PAD_Y * 2 + _TAIL_H)

        self.reposition()   # 先定位置与尾巴方向，再摆文字
        top = _PAD_Y + (_TAIL_H if self._tail_up else 0)
        self._label.setGeometry(_PAD_X, top, label_w, label_h)
        self._label.setText(text)

        self.show()
        self.raise_()
        self._hide_timer.start(duration)

    def reposition(self):
        """跟随锚定窗口定位：默认贴头顶，顶部放不下则翻到身体下方。"""
        if self._anchor is None:
            return
        ag = self._anchor.frameGeometry()
        screen = QGuiApplication.screenAt(ag.center()) or QGuiApplication.primaryScreen()
        sgeo = screen.availableGeometry()

        x = ag.center().x() - self.width() // 2
        y = ag.top() - self.height() + _TAIL_H - 2   # 气泡底边贴在头顶上方
        self._tail_up = False
        if y < sgeo.top():                           # 屏幕顶部空间不足 -> 翻到下方
            y = ag.bottom() - _TAIL_H + 2
            self._tail_up = True
        x = max(sgeo.left() + 4, min(x, sgeo.right() - self.width() - 4))
        self.move(x, y)

    # ------------------------------------------------------------ 自绘气泡
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx = w / 2.0

        path = QPainterPath()
        if self._tail_up:
            body = QRectF(2, 2 + _TAIL_H, w - 4, h - _TAIL_H - 4)
            path.addRoundedRect(body, 10, 10)
            path.moveTo(cx - 7, _TAIL_H + 2)
            path.lineTo(cx + 7, _TAIL_H + 2)
            path.lineTo(cx, 2)
        else:
            body = QRectF(2, 2, w - 4, h - _TAIL_H - 4)
            path.addRoundedRect(body, 10, 10)
            path.moveTo(cx - 7, h - _TAIL_H - 2)
            path.lineTo(cx + 7, h - _TAIL_H - 2)
            path.lineTo(cx, h - 2)
        path.closeSubpath()

        p.fillPath(path, QColor(255, 255, 255, 235))
        p.setPen(QPen(QColor(110, 110, 110, 150), 1))
        p.drawPath(path)
