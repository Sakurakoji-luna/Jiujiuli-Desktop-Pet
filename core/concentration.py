# -*- coding: utf-8 -*-
"""神经衰弱（翻牌记忆）小游戏（右键菜单入口）。

- ConcentrationGame：纯逻辑模型，默认 8 对牌（4x4），可独立测试。
  双方轮流翻两张：同点数配对成功可继续翻，否则翻回并换人；
  全部取完后对数多者获胜。
- ConcentrationDialog：Qt 界面，复用扑克牌素材（core.old_maid 的
  牌背样式与 card_file 映射）。玖玖里 AI 会记住双方翻过的牌，
  已知成对的优先拿走（符合角色“记忆力惊人”的设定）。
"""
import os
import random

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QGridLayout, QHBoxLayout,
                               QLabel, QPushButton, QVBoxLayout)

from core import config, settings
from core.old_maid import CARD_BACK_QSS, CARD_RATIO, RANKS, SUITS, card_file

_FLIP_BACK_MS = 900      # 未配对：翻回前展示时长
_PAIR_DONE_MS = 500      # 配对成功：标记取走前展示时长
_AI_STEP_MS = 650        # 玖玖里两张翻牌之间的间隔

CARD_W = 86
CARD_H = round(CARD_W * CARD_RATIO)

# 牌面朝上的按钮样式（正面图 + 取走后绿色描边）
_FACE_QSS = "QPushButton { background: transparent; border: 3px solid transparent; border-radius: 6px; }"
_TAKEN_QSS = "QPushButton { background: transparent; border: 3px solid #2e7d32; border-radius: 6px; }"


class ConcentrationGame:
    def __init__(self, pairs=None, difficulty=None):
        pairs = pairs or config.CONCENTRATION_PAIRS
        self.difficulty = difficulty or config.CONCENTRATION_DEFAULT_DIFFICULTY
        ranks = random.sample(RANKS, pairs)
        deck = [(r, s) for r in ranks for s in random.sample(SUITS, 2)]
        random.shuffle(deck)
        self.board = deck
        self.revealed = [False] * len(deck)
        self.taken = [False] * len(deck)
        self.known = set()          # 双方翻过的位置（玖玖里的记忆）
        self.player_pairs = 0
        self.ai_pairs = 0
        self.turn = "player"
        self.picked = []
        self.last_pair = None       # 最近一次翻开的两张 (a, b)
        self.winner = None          # "player" / "ai" / "draw" / None

    def _rank(self, i):
        return self.board[i][0]

    # ---------------------------------------------------------------- 玩家
    def can_pick(self, i):
        return (self.turn == "player" and self.winner is None
                and not self.revealed[i] and not self.taken[i]
                and len(self.picked) < 2)

    def player_pick(self, i):
        """翻开 i；凑满两张结算。返回 continue / match / miss / end。"""
        if not self.can_pick(i):
            return "continue"
        self.revealed[i] = True
        self.known.add(i)
        self.picked.append(i)
        if len(self.picked) < 2:
            return "continue"
        a, b = self.picked
        self.picked = []
        self.last_pair = (a, b)
        if self._rank(a) == self._rank(b):
            self.player_pairs += 1
            self.taken[a] = self.taken[b] = True
            self._check_end()
            return "end" if self.winner else "match"
        self.turn = "ai"
        return "miss"

    def flip_back(self, a, b):
        """未配对的两张翻回。"""
        self.revealed[a] = False
        self.revealed[b] = False

    # ---------------------------------------------------------------- 玖玖里
    def ai_forget(self):
        """记忆遗忘：已知牌数超过阈值后，每回合按难度随机遗忘部分位置。

        返回本次遗忘的张数。全力模式概率为 0（完美记忆）。
        """
        if len(self.known) <= config.CONCENTRATION_FORGET_THRESHOLD:
            return 0
        rate = config.CONCENTRATION_FORGET_RATE.get(self.difficulty, 0.0)
        if rate <= 0:
            return 0
        forgotten = [i for i in self.known if random.random() < rate]
        self.known.difference_update(forgotten)
        return len(forgotten)

    def ai_choose(self):
        """AI 决策：记忆里已有同点数两张 -> 直接拿；否则先翻未知牌，
        再翻记忆中同点数的另一张。"""
        memory = {}
        for i in self.known:
            if not self.taken[i]:
                memory.setdefault(self._rank(i), []).append(i)
        for idxs in memory.values():
            if len(idxs) >= 2:
                return idxs[0], idxs[1]
        unseen = [i for i in range(len(self.board))
                  if not self.taken[i] and i not in self.known]
        first = random.choice(unseen)
        mate = [i for i in memory.get(self._rank(first), [])]
        rest = [i for i in unseen if i != first]
        second = mate[0] if mate else (random.choice(rest) if rest else first)
        return first, second

    def ai_flip(self, i, j):
        """玖玖里翻开两张并结算。返回 match / miss / end。"""
        self.revealed[i] = True
        self.revealed[j] = True
        self.known.update((i, j))
        self.last_pair = (i, j)
        if self._rank(i) == self._rank(j):
            self.ai_pairs += 1
            self.taken[i] = self.taken[j] = True
            self._check_end()
            return "end" if self.winner else "match"
        self.turn = "player"
        return "miss"

    def _check_end(self):
        if all(self.taken):
            if self.player_pairs > self.ai_pairs:
                self.winner = "player"
            elif self.player_pairs < self.ai_pairs:
                self.winner = "ai"
            else:
                self.winner = "draw"


class ConcentrationDialog(QDialog):
    """神经衰弱游戏窗口：4x4 牌背网格，翻开的牌显示扑克牌素材。"""

    def __init__(self, router=None, parent=None):
        super().__init__(parent)
        self._router = router
        self.setWindowTitle("神经衰弱")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)

        self._game = None
        self._btns = []
        self._lock = False        # 动画进行中禁止点击
        self._pm_cache = {}
        self._ai_pending = None   # AI 待翻的 (i, j)

        self._scores = QLabel()
        self._difficulty = QComboBox()
        self._difficulty.addItems(list(config.CONCENTRATION_FORGET_RATE))
        saved = settings.load_settings().get(
            "concentration_difficulty", config.CONCENTRATION_DEFAULT_DIFFICULTY)
        if saved in config.CONCENTRATION_FORGET_RATE:
            self._difficulty.setCurrentText(saved)
        self._difficulty.currentTextChanged.connect(self._on_difficulty)
        top_row = QHBoxLayout()
        top_row.addWidget(self._scores)
        top_row.addStretch(1)
        top_row.addWidget(QLabel("难度:"))
        top_row.addWidget(self._difficulty)

        self._status = QLabel()
        self._status.setWordWrap(True)
        grid = QGridLayout()
        for i in range(config.CONCENTRATION_PAIRS * 2):
            btn = QPushButton("")
            btn.setFixedSize(CARD_W, CARD_H)
            btn.setIconSize(btn.size())
            btn.clicked.connect(
                lambda checked=False, idx=i: self._on_click(idx))
            grid.addWidget(btn, i // 4, i % 4)
            self._btns.append(btn)
        self._again_btn = QPushButton("再来一局")
        self._again_btn.clicked.connect(self.new_game)

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addLayout(grid)
        layout.addWidget(self._status)
        layout.addWidget(self._again_btn)

        self._flipback_timer = QTimer(self)
        self._flipback_timer.setSingleShot(True)
        self._flipback_timer.timeout.connect(self._on_flip_back)
        self._pair_timer = QTimer(self)
        self._pair_timer.setSingleShot(True)
        self._pair_timer.timeout.connect(self._on_pair_done)
        self._ai_timer = QTimer(self)
        self._ai_timer.setSingleShot(True)
        self._ai_timer.timeout.connect(self._ai_step)

        self.new_game()

    # ---------------------------------------------------------------- 素材
    def _card_icon(self, i):
        key = self._game.board[i]
        if key not in self._pm_cache:
            pm = QPixmap(os.path.join(config.CARD_DIR, card_file(key)))
            if pm.isNull():
                self._pm_cache[key] = None
            else:
                self._pm_cache[key] = pm.scaled(
                    CARD_W - 8, CARD_H - 8, Qt.KeepAspectRatio,
                    Qt.SmoothTransformation)
        pm = self._pm_cache[key]
        return QIcon(pm) if pm is not None else None

    # ---------------------------------------------------------------- 流程
    def _on_difficulty(self, text):
        """切换难度：应用到当前对局并持久化。"""
        if self._game is not None:
            self._game.difficulty = text
        data = settings.load_settings()
        data["concentration_difficulty"] = text
        settings.save_settings(data)

    def new_game(self):
        self._game = ConcentrationGame(
            difficulty=self._difficulty.currentText())
        self._lock = False
        self._ai_pending = None
        self._refresh()
        self._status.setText("开局：你先请。翻开两张牌吧。")

    def _on_click(self, i):
        if self._lock:
            return
        result = self._game.player_pick(i)
        if result == "continue":
            self._refresh()
            self._status.setText("再翻一张。")
            return
        self._lock = True
        self._refresh()
        if result == "match":
            self._status.setText("配对成功！可以再翻一次。")
            self._pair_timer.start(_PAIR_DONE_MS)
        elif result == "miss":
            self._status.setText("没配对……换玖玖里了。")
            self._flipback_timer.start(_FLIP_BACK_MS)
        else:   # end
            self._finish()

    def _on_pair_done(self):
        if self._game.winner:
            self._finish()
        elif self._game.turn == "player":
            self._lock = False   # 先解锁再刷新，按钮状态才会恢复
            self._refresh()
            self._status.setText("继续翻两张。")
        else:   # 玖玖里配对成功，继续她的回合
            self._start_ai_turn()

    def _on_flip_back(self):
        if self._game.last_pair:
            self._game.flip_back(*self._game.last_pair)
        if self._game.winner:
            self._finish()
        elif self._game.turn == "player":
            self._lock = False   # 先解锁再刷新
            self._refresh()
            self._status.setText("轮到你了。")
        else:
            self._start_ai_turn()

    # ---------------------------------------------------------------- 玖玖里
    def _start_ai_turn(self):
        if self._game.winner or self._game.turn != "ai":
            return
        self._lock = True
        forgotten = self._game.ai_forget()
        line = "玖玖里正在思考……"
        if forgotten and random.random() < 0.5:
            line += f"（她好像忘了点什么？）"
        elif self._router and random.random() < 0.4:
            taunt = self._router.get_pool_line("concentration")[0]
            if taunt:
                line += " 「" + taunt + "」"
        self._status.setText(line)
        self._ai_pending = self._game.ai_choose()
        self._game.revealed[self._ai_pending[0]] = True
        self._game.known.add(self._ai_pending[0])
        self._refresh()
        self._ai_timer.start(_AI_STEP_MS)

    def _ai_step(self):
        i, j = self._ai_pending
        result = self._game.ai_flip(i, j)
        self._refresh()
        if result == "match":
            self._status.setText("玖玖里配对成功！")
            self._pair_timer.start(_PAIR_DONE_MS)
        elif result == "miss":
            self._status.setText("玖玖里也没翻对。")
            self._flipback_timer.start(_FLIP_BACK_MS)
        else:
            self._finish()

    # ---------------------------------------------------------------- 收尾
    def _finish(self):
        self._refresh()
        if self._game.winner == "player":
            self._status.setText("你赢了。……哼，你的记性什么时候变得这么好了？")
        elif self._game.winner == "ai":
            self._status.setText("我赢了哦。这种靠记忆力的游戏，你赢不了我的。")
        else:
            self._status.setText("平手……哼，下次可不会了。")

    def _refresh(self):
        g = self._game
        self._scores.setText(
            f"你：{g.player_pairs} 对    玖玖里：{g.ai_pairs} 对")
        for i, btn in enumerate(self._btns):
            if g.taken[i]:
                btn.setIcon(self._card_icon(i))
                btn.setStyleSheet(_TAKEN_QSS)
                btn.setEnabled(False)
            elif g.revealed[i]:
                btn.setIcon(self._card_icon(i))
                btn.setStyleSheet(_FACE_QSS)
                btn.setEnabled(False)
            else:
                btn.setIcon(QIcon())
                btn.setStyleSheet(CARD_BACK_QSS)
                btn.setEnabled(not self._lock and g.turn == "player"
                               and g.winner is None)
