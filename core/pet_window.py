# -*- coding: utf-8 -*-
"""透明无边框桌宠窗口：单帧展示 + 鼠标拖拽 + 右键菜单（登录/对话/退出）。

- Qt.FramelessWindowHint + WA_TranslucentBackground：只渲染角色图像。
- 左键：位移小于 DRAG_THRESHOLD 视为“点击”（触发换图），否则视为拖拽。
- 右键菜单：登录（API 接入）/ 对话（AI 聊天）/ 退出。
- 窗口位置持久化到 data/settings.json，重启后回到上次位置。
"""
from PySide6.QtCore import Qt, QPoint, QTimer, Signal
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QWidget

from core import config, settings


class PetWindow(QWidget):
    clicked = Signal()           # 左键单击（非拖拽）
    double_clicked = Signal()    # 左键快速双击
    dragged = Signal()           # 拖拽结束
    moved = Signal()             # 拖动中
    login_requested = Signal()   # 右键菜单 -> 登录
    chat_requested = Signal()    # 右键菜单 -> 对话
    game_requested = Signal()          # 右键菜单 -> 抽鬼牌
    concentration_requested = Signal() # 右键菜单 -> 神经衰弱
    hide_requested = Signal()    # 右键菜单 -> 隐藏
    active_mode_toggled = Signal(bool)   # 右键菜单 -> 活跃模式开关

    def __init__(self, active_mode=True):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._label = QLabel(self)
        self._label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._label.setAlignment(Qt.AlignCenter)

        self._drag_offset = None   # 拖拽时鼠标相对窗口左上角的偏移
        self._press_pos = None     # 按下位置，用于区分点击/拖拽
        self._dragged = False
        self._double_pending = False   # 等待判断单击/双击

        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._fire_click)

        self._build_menu(active_mode)
        self._restore_position()

    # ---------------------------------------------------------------- 显示
    def set_pixmap(self, pixmap):
        """展示一张图（窗口尺寸跟随图片）。"""
        if self.width() != pixmap.width() or self.height() != pixmap.height():
            self.setFixedSize(pixmap.width(), pixmap.height())
        self._label.setPixmap(pixmap)
        self._label.setFixedSize(pixmap.width(), pixmap.height())

    # ------------------------------------------------------------ 右键菜单
    def _build_menu(self, active_mode):
        self._menu = QMenu(self)
        login_act = QAction("登录", self._menu)
        login_act.triggered.connect(self.login_requested)
        chat_act = QAction("对话", self._menu)
        chat_act.triggered.connect(self.chat_requested)
        game_act = QAction("抽鬼牌", self._menu)
        game_act.triggered.connect(self.game_requested)
        concentration_act = QAction("神经衰弱", self._menu)
        concentration_act.triggered.connect(self.concentration_requested)
        active_act = QAction("活跃模式", self._menu)
        active_act.setCheckable(True)
        active_act.setChecked(active_mode)
        active_act.toggled.connect(self.active_mode_toggled)
        hide_act = QAction("隐藏", self._menu)
        hide_act.triggered.connect(self.hide_requested)
        quit_act = QAction("退出", self._menu)
        quit_act.triggered.connect(QGuiApplication.instance().quit)
        self._menu.addAction(login_act)
        self._menu.addAction(chat_act)
        self._menu.addAction(game_act)
        self._menu.addAction(concentration_act)
        self._menu.addSeparator()
        self._menu.addAction(active_act)
        self._menu.addAction(hide_act)
        self._menu.addSeparator()
        self._menu.addAction(quit_act)

    # ---------------------------------------------------------------- 交互
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            pos = e.globalPosition().toPoint()
            self._drag_offset = pos - self.frameGeometry().topLeft()
            self._press_pos = pos
        elif e.button() == Qt.RightButton:
            self._menu.exec(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if self._drag_offset is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_offset)
            self.moved.emit()
            if (e.globalPosition().toPoint() - self._press_pos).manhattanLength() \
                    >= config.DRAG_THRESHOLD:
                self._dragged = True

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            if self._dragged:
                self.dragged.emit()
            else:
                self._queue_click()
            self._drag_offset = None
            self._press_pos = None
            self._dragged = False
            self.save_position()

    def _queue_click(self):
        """单击/双击消歧：第二次点击落在系统双击间隔内则取消单击、触发双击。"""
        if self._double_pending:
            self._click_timer.stop()
            self._double_pending = False
            self.double_clicked.emit()
        else:
            self._double_pending = True
            self._click_timer.start(QApplication.doubleClickInterval())

    def _fire_click(self):
        self._double_pending = False
        self.clicked.emit()

    # ------------------------------------------------------------ 位置持久化
    def _restore_position(self):
        pos = settings.load_settings().get("pos")
        screen = QGuiApplication.primaryScreen().availableGeometry()
        if pos and screen.contains(QPoint(pos[0], pos[1])):
            self.move(QPoint(pos[0], pos[1]))
        else:
            # 默认停在主屏右下角
            self.move(screen.right() - self.width() - 40,
                      screen.bottom() - self.height() - 40)

    def save_position(self):
        data = settings.load_settings()
        data["pos"] = [self.x(), self.y()]
        settings.save_settings(data)
