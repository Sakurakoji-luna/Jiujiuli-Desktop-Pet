# -*- coding: utf-8 -*-
"""抽鬼牌小游戏（右键菜单入口）。

- OldMaidGame：纯逻辑模型，53 张牌（52 张 + 小丑），可独立测试。
  玩家回合抽玖玖里的牌，抽到与手牌同点数的牌自动成对弃掉；
  玖玖里回合随机抽玩家的牌。手牌先清空者获胜（另一方持小丑落败）。
- OldMaidDialog：Qt 界面。牌面用字符表示（♠A / 🃏），玖玖里的手牌
  背面朝上显示为 🂠，玩家回合点击抽取。
"""
import os
import random
import time

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout)

from core import config

SUITS = "♠♥♦♣"
RANKS = "A23456789TJQK"
JOKER = ("JOKER", "🃏")

# 扑克牌素材：resource/其他/扑克牌/png/（如 "AS.png"、"10H.png"、"Joker1.png"）
_SUIT_LETTER = {"♠": "S", "♥": "H", "♦": "D", "♣": "C"}

CARD_RATIO = 437 / 300   # 扑克牌素材高/宽比（300x437）

# 牌背样式（无背面素材，用渐变圆角模拟）
CARD_BACK_QSS = (
    "QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
    " stop:0 #2e63b8, stop:1 #173e7c); border: 2px solid #dfe6f3;"
    " border-radius: 6px; }"
    "QPushButton:hover { border-color: #ffffff; }"
    "QPushButton:disabled { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
    " stop:0 #3a6db8, stop:1 #2a4f8c); }"
)


def card_file(card):
    """(rank, suit) -> 扑克牌素材文件名；无对应素材返回 None。"""
    rank, suit = card
    if rank == "JOKER":
        return "Joker1.png"
    letter = _SUIT_LETTER.get(suit)
    if letter is None:
        return None
    r = "10" if rank == "T" else rank
    return f"{r}{letter}.png"


def card_text(card):
    rank, suit = card
    return "🃏" if rank == "JOKER" else suit + rank


class OldMaidGame:
    def __init__(self):
        self.player_hand = []
        self.ai_hand = []
        self.turn = "player"
        self.winner = None      # "player" / "ai" / None
        self.last_draw = None
        self._deal()

    # ---------------------------------------------------------------- 发牌
    def _deal(self):
        deck = [(r, s) for s in SUITS for r in RANKS] + [JOKER]
        random.shuffle(deck)
        self.player_hand = deck[:27]
        self.ai_hand = deck[27:]
        self._discard_pairs(self.player_hand)
        self._discard_pairs(self.ai_hand)
        self._check_end()   # 弃对后可能已有空手牌，需立即结算

    @staticmethod
    def _discard_pairs(hand):
        """同点数两张成对弃掉（小丑点数唯一，不会成对）。"""
        hand.sort(key=lambda c: c[0])
        i = 0
        while i < len(hand) - 1:
            if hand[i][0] == hand[i + 1][0]:
                del hand[i:i + 2]
            else:
                i += 1

    # ---------------------------------------------------------------- 走牌
    def draw_from_ai(self, index):
        """玩家回合：抽玖玖里手中 index 位置的牌。返回抽到的牌或 None。"""
        if self.turn != "player" or not (0 <= index < len(self.ai_hand)):
            return None
        card = self.ai_hand.pop(index)
        self.player_hand.append(card)
        self.last_draw = card
        self._discard_pairs(self.player_hand)
        self._check_end()
        if self.winner is None:
            self.turn = "ai"
        return card

    def ai_turn(self):
        """玖玖里回合：随机抽玩家一张牌。返回抽到的牌或 None。"""
        if self.turn != "ai" or not self.player_hand:
            return None
        card = self.player_hand.pop(random.randrange(len(self.player_hand)))
        self.ai_hand.append(card)
        self.last_draw = card
        self._discard_pairs(self.ai_hand)
        self._check_end()
        if self.winner is None:
            self.turn = "player"
        return card

    def _check_end(self):
        # 手牌清空者获胜（小丑必然在另一方手中）
        if not self.ai_hand:
            self.winner = "ai"
        elif not self.player_hand:
            self.winner = "player"


class OldMaidDialog(QDialog):
    """抽鬼牌游戏窗口：上行玖玖里（牌背可点击），下行玩家（明牌素材）。"""

    def __init__(self, router=None, on_line=None, parent=None):
        super().__init__(parent)
        self._router = router
        self._on_line = on_line   # 悬停台词回调 (text, emotion)
        self._last_hover_at = 0.0
        self.setWindowTitle("抽鬼牌")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setFixedWidth(700)

        self._game = None
        self._card_btns = []
        self._pm_cache = {}   # (card, width) -> QPixmap

        self._ai_label = QLabel()
        self._ai_row = QHBoxLayout()
        self._status = QLabel()
        self._status.setWordWrap(True)
        self._player_label = QLabel()
        self._player_row = QHBoxLayout()

        self._again_btn = QPushButton("再来一局")
        self._again_btn.clicked.connect(self.new_game)

        layout = QVBoxLayout(self)
        layout.addWidget(self._ai_label)
        layout.addLayout(self._ai_row)
        layout.addWidget(self._status)
        layout.addWidget(self._player_label)
        layout.addLayout(self._player_row)
        layout.addWidget(self._again_btn)

        self._ai_timer = QTimer(self)
        self._ai_timer.setSingleShot(True)
        self._ai_timer.timeout.connect(self._do_ai_turn)

        self.new_game()

    # ---------------------------------------------------------------- 素材
    def _card_pixmap(self, card, w):
        """按宽度取缩放后的扑克牌素材；素材缺失返回 None（降级为文字牌）。"""
        fname = card_file(card)
        if fname is None:
            return None
        key = (card, w)
        if key not in self._pm_cache:
            pm = QPixmap(os.path.join(config.CARD_DIR, fname))
            if pm.isNull():
                self._pm_cache[key] = None
            else:
                self._pm_cache[key] = pm.scaledToHeight(
                    max(1, round(w * CARD_RATIO)), Qt.SmoothTransformation)
        return self._pm_cache[key]

    # ---------------------------------------------------------------- 流程
    def new_game(self):
        self._game = OldMaidGame()
        self._render()

    def _render(self, status_text=None):
        """重绘牌面；status_text 为抽牌反馈等临时文案（胜负文案优先）。"""
        g = self._game
        # 清空旧按钮
        for w in self._card_btns:
            w.deleteLater()
        self._card_btns = []

        # 牌宽按双方最大手牌数动态缩放，保证一行放得下
        n = max(len(g.ai_hand), len(g.player_hand), 1)
        card_w = max(30, min(58, (self.width() - 48) // n - 4))
        card_h = max(1, round(card_w * CARD_RATIO))

        self._ai_label.setText(f"玖玖里（{len(g.ai_hand)} 张）")
        for i in range(len(g.ai_hand)):
            btn = QPushButton("")
            btn.setFixedSize(card_w, card_h)
            btn.setStyleSheet(CARD_BACK_QSS)
            btn.setEnabled(g.turn == "player" and g.winner is None)
            btn.clicked.connect(lambda checked=False, idx=i: self._player_draw(idx))
            btn.installEventFilter(self)   # 悬停触发互动台词
            self._ai_row.addWidget(btn)
            self._card_btns.append(btn)

        self._player_label.setText(f"你（{len(g.player_hand)} 张）")
        while self._player_row.count():
            item = self._player_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for card in sorted(g.player_hand, key=lambda c: c[0]):
            pm = self._card_pixmap(card, card_w)
            if pm is not None:
                lbl = QLabel()
                lbl.setPixmap(pm)
                lbl.setFixedSize(pm.size())
            else:   # 素材缺失兜底：文字牌
                lbl = QLabel(card_text(card))
                lbl.setFixedSize(card_w, card_h)
                lbl.setAlignment(Qt.AlignCenter)
            self._player_row.addWidget(lbl)
        self._player_row.addStretch(1)

        if g.winner:
            if g.winner == "player":
                self._status.setText("你赢了。……哼，这局只是我大意了，别得意忘形。")
            else:
                self._status.setText("我赢了哦。早就说过，你赢不了我的。")
        elif status_text:
            self._status.setText(status_text)
        elif g.turn == "player":
            self._status.setText("轮到你了。从玖玖里手中抽一张牌吧。")
        else:
            self._status.setText("玖玖里正在抽牌……")

    def _player_draw(self, index):
        g = self._game
        card = g.draw_from_ai(index)
        if card is None:
            return
        paired = card[0] not in [c[0] for c in g.player_hand]
        text = card_text(card)
        msg = f"你抽到了 {text}。" + ("正好凑成一对，丢掉了！" if paired else "")
        if g.winner is None:
            self._render(status_text=msg)
            # 玖玖里回合（延迟一点，更有打牌的感觉）
            self._ai_timer.start(config.OLD_MAID_AI_DELAY_MS)
        else:
            self._render()   # 分胜负：显示胜负文案

    # ------------------------------------------------------------ 悬停互动
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Enter and obj in self._card_btns:
            self._on_card_hover(self._card_btns.index(obj))
        return super().eventFilter(obj, event)

    def _on_card_hover(self, index):
        """悬停玖玖里的牌：按概率触发互动台词（鬼牌台词有微妙变化）。

        台词通过 on_line 回调交给主程序 -> 气泡显示 + 按情绪词换 PNG
        （逻辑与「对话和PNG不对应」一致）。
        """
        g = self._game
        if (self._on_line is None or self._router is None
                or g.winner is not None or g.turn != "player"
                or index >= len(g.ai_hand)):
            return
        now = time.monotonic()
        if now - self._last_hover_at < config.OLD_MAID_HOVER_COOLDOWN_MS / 1000:
            return
        is_joker = g.ai_hand[index][0] == "JOKER"
        chance = (config.OLD_MAID_HOVER_JOKER_CHANCE if is_joker
                  else config.OLD_MAID_HOVER_CHANCE)
        if random.random() >= chance:
            return
        pool = "old_maid_hover_joker" if is_joker else "old_maid_hover"
        text, emo = self._router.get_pool_line(pool)
        if text:
            self._last_hover_at = now
            self._on_line(text, emo)

    def _do_ai_turn(self):
        g = self._game
        card = g.ai_turn()
        if card is None:
            return
        text = card_text(card)
        line = f"玖玖里抽走了你的 {text}。"
        if self._router and random.random() < 0.5:
            taunt = self._router.get_pool_line("old_maid")[0]
            if taunt:
                line += " 「" + taunt + "」"
        self._render(status_text=line)
