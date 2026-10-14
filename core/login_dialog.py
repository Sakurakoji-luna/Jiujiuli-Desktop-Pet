# -*- coding: utf-8 -*-
"""登录对话框：接入 AI API 服务（如 DeepSeek），并检测网址与 Key 是否可用。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QVBoxLayout)

from core import config


class LoginDialog(QDialog):
    def __init__(self, api, parent=None):
        super().__init__(parent)
        self._api = api
        # 与游戏窗口/气泡一致置顶：否则会开在终端、浏览器等其他窗口后面，
        # 用户点击“登录”看不到任何窗口弹出。
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("登录 - AI API 接入")
        self.setFixedWidth(440)

        self._url = QLineEdit(api.base_url)
        self._url.setPlaceholderText(config.API_DEFAULT_BASE)
        self._key = QLineEdit(api.api_key)
        self._key.setEchoMode(QLineEdit.Password)
        self._key.setPlaceholderText("sk-...")
        self._model = QLineEdit(api.model)
        self._model.setPlaceholderText(config.API_DEFAULT_MODEL)

        form = QFormLayout()
        form.addRow("API 地址:", self._url)
        form.addRow("API Key:", self._key)
        form.addRow("模型:", self._model)

        self._status = QLabel(self._status_text())
        self._status.setWordWrap(True)

        self._btn_test = QPushButton("测试连接")
        self._btn_test.clicked.connect(self._run_test)
        self._btn_save = QPushButton("保存")
        self._btn_save.clicked.connect(self._save)
        self._btn_cancel = QPushButton("取消")
        self._btn_cancel.clicked.connect(self.reject)

        btns = QHBoxLayout()
        btns.addWidget(self._btn_test)
        btns.addStretch(1)
        btns.addWidget(self._btn_save)
        btns.addWidget(self._btn_cancel)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._status)
        layout.addLayout(btns)

    def _status_text(self):
        return "✓ 已连接" if self._api.verified else "○ 未连接"

    def _run_test(self):
        self._status.setText("正在检测……")
        self._status.setStyleSheet("color: #555;")
        self._btn_test.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            ok, msg = self._api.test(self._url.text().strip(),
                                     self._key.text().strip(),
                                     self._model.text().strip())
        finally:
            QApplication.restoreOverrideCursor()
            self._btn_test.setEnabled(True)
        self._status.setText(("✓ " if ok else "✗ ") + msg)
        self._status.setStyleSheet("color: %s;" % ("#1a7f37" if ok else "#c62828"))
        return ok

    def _save(self):
        """保存前必须通过连通性检测。"""
        if not self._run_test():
            return
        self._api.base_url = self._url.text().strip()
        self._api.api_key = self._key.text().strip()
        self._api.model = self._model.text().strip()
        self._api.verified = True
        self._api.save()
        self.accept()
