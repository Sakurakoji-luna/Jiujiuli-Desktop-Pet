# -*- coding: utf-8 -*-
"""聊天输入浮层（issue 优化）：贴在桌宠所在屏幕底部的透明输入栏。

- 素材 resource/其他/聊天框.png 为 1280x720 全屏设计，非透明内容只有底部
  输入栏（约 y=535~720）。浮层按屏幕宽度等比缩放、底部对齐屏幕可用区域。
- setMask(alpha)：输入栏以外的区域完全鼠标穿透，不挡桌面操作。
- Enter 发送（submitted 信号）；Esc、右上角 ×、或点击浮层外任意位置
  （窗口失活）关闭。
- 请求在后台线程执行（ChatWorker），等待期间输入框禁用。
"""
import os

from PySide6.QtCore import QEvent, QObject, Qt, QRectF, Signal
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QPainter,
                           QPainterPath, QPen, QPixmap, QRegion)
from PySide6.QtWidgets import QLineEdit, QToolButton, QWidget

from core import config

_BAND_TOP_RATIO = 535 / 720   # 素材中输入栏顶边（来自 alpha 包围盒）
_INPUT_X_RATIO = 0.12         # 输入框水平留白比例


class ChatInputBox(QWidget):
    submitted = Signal(str)    # 用户按下 Enter 提交的消息

    def __init__(self, parent=None):
        super().__init__(None)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        src_path = os.path.join(config.RESOURCE_DIR, "其他", "聊天框.png")
        self._src = QPixmap(src_path)
        self._bg = QPixmap()
        self._screen_key = None

        self._input = QLineEdit(self)
        self._input.setFont(QFont("Microsoft YaHei", 11))
        self._input.setStyleSheet(
            "QLineEdit { background: transparent; border: none; color: #333; }")
        self._input.setPlaceholderText("输入消息，Enter 发送，Esc 关闭")
        self._input.returnPressed.connect(self._send)
        self._input.installEventFilter(self)

        self._close_btn = QToolButton(self)
        self._close_btn.setText("×")
        self._close_btn.setStyleSheet(
            "QToolButton { background: transparent; border: none;"
            " color: #999; font-size: 15px; font-weight: bold; }"
            "QToolButton:hover { color: #444; }")
        self._close_btn.setFixedSize(20, 20)
        self._close_btn.clicked.connect(self.hide)

        self._busy = False

    # ------------------------------------------------------------------ 布局
    def _build_overlay(self, screen):
        """按屏幕尺寸缩放素材，底部对齐，并设置 alpha 蒙版。"""
        geo = screen.availableGeometry()
        if self._src.isNull():
            # 素材缺失兜底：底部画一条普通输入栏，蒙版为整条矩形
            self._w = geo.width()
            self._h = min(140, round(geo.height() * 0.2))
            self._band_top = self._h - min(84, self._h - 20)
            self._scale = 1.0
            self._bg = QPixmap()
            band = QRegion(0, self._band_top, self._w, self._h - self._band_top)
            self.setMask(band)
        else:
            scale = geo.width() / self._src.width()
            self._scale = scale
            self._bg = self._src.scaled(
                round(self._src.width() * scale),
                round(self._src.height() * scale),
                Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._w, self._h = self._bg.width(), self._bg.height()
            self._band_top = round(self._h * _BAND_TOP_RATIO)
            self.setMask(self._bg.mask())   # 只有素材实体区域接收鼠标
        self.setFixedSize(self._w, self._h)
        self.move(geo.left(), geo.bottom() - self._h + 1)
        self._relayout()

    def _relayout(self):
        band_h = self._h - self._band_top
        input_h = max(28, min(round(40 * self._scale), band_h - 8))
        input_x = round(self._w * _INPUT_X_RATIO)
        self._input.setFont(QFont("Microsoft YaHei",
                                  max(11, min(round(14 * self._scale), 22))))
        self._input.setGeometry(input_x,
                                self._band_top + (band_h - input_h) // 2,
                                self._w - input_x * 2, input_h)
        self._close_btn.move(self._w - 30,
                             self._band_top + (band_h - 20) // 2)

    # ------------------------------------------------------------------ API
    def show_box(self, anchor):
        """在 anchor（桌宠）所在屏幕底部显示输入栏并聚焦。"""
        screen = (QGuiApplication.screenAt(anchor.frameGeometry().center())
                  or QGuiApplication.primaryScreen())
        key = (screen.geometry().width(), screen.geometry().height(),
               screen.availableGeometry().bottom())
        if key != self._screen_key:
            self._screen_key = key
            self._build_overlay(screen)
        self.show()
        self.raise_()
        self.activateWindow()
        self._input.setFocus()
        self._input.selectAll()

    def set_busy(self, busy):
        """等待 AI 回复期间禁用输入。"""
        self._busy = busy
        self._input.setEnabled(not busy)
        self._input.setPlaceholderText(
            "等待回复……" if busy else "输入消息，Enter 发送，Esc 关闭")

    # ---------------------------------------------------------------- 交互
    def _send(self):
        text = self._input.text().strip()
        if not text or self._busy:
            return
        self._input.clear()
        self.submitted.emit(text)

    def eventFilter(self, obj, event):
        if (obj is self._input
                and event.type() == QEvent.Type.KeyPress
                and event.key() == Qt.Key_Escape):
            self.hide()
            return True
        return super().eventFilter(obj, event)

    def changeEvent(self, event):
        # 点击浮层以外的任何位置（窗口失活）即关闭
        if event.type() == QEvent.Type.WindowDeactivate:
            self.hide()
        super().changeEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        if not self._bg.isNull():
            p.drawPixmap(0, 0, self._bg)
            return
        # 兜底：白色圆角输入栏
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(2, self._band_top,
                                   self.width() - 4,
                                   self.height() - self._band_top - 2), 12, 12)
        p.fillPath(path, QColor(255, 255, 255, 235))
        p.setPen(QPen(QColor(110, 110, 110, 150), 1))
        p.drawPath(path)


class ChatWorker(QObject):
    """跑在子线程里的 AI 请求执行器，通过信号把结果投递回主线程。

    engine: TavernPromptEngine（组装角色卡/世界书/历史/后置指令，解析情绪标签）
    env_getter: 返回天气环境文本的可调用对象（子线程内只读缓存，安全）
    """
    reply = Signal(str, str)    # (纯文本台词, 情绪标签)
    failed = Signal(str)

    def __init__(self, api, engine, env_getter=None):
        super().__init__()
        self._api = api
        self._engine = engine
        self._env_getter = env_getter

    def run(self, text):
        try:
            env = self._env_getter() if self._env_getter else "未知"
            messages = self._engine.build_messages(text, current_weather=env)
            raw = self._api.chat_messages(messages)
            clean, emotion = self._engine.parse_ai_response(raw, text)
            self.reply.emit(clean, emotion)
        except Exception as exc:
            self.failed.emit(str(exc))
