# -*- coding: utf-8 -*-
"""图片库与装扮选择（V2 表情轮询机制，替代旧帧轮播动画）。

- 扫描 resource/ 下全部装扮文件夹（夏装/冬装/秋装/家居），每个装扮下按
  1,2,3... 子文件夹分组（动作连贯分组，同组 PNG 相似），全部预加载进内存。
- 无帧轮播动画：pick_random() 在当前装扮下随机选分组、随机取一张图展示，
  返回该图的表情标签（文件名含 EMOTION_TAGS 之一），无标签返回 None。
- choose_outfit()：深夜（22:00~6:00）强制家居；其余按温度 + 天气选装扮。
"""
import os
import random

from PySide6.QtCore import QObject, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap

from core import config


def choose_outfit(hour, temp_c, condition):
    """按 V2 文档规则选择装扮。temp_c 为 None 时回退默认装扮。"""
    if hour >= config.NIGHT_START or hour < config.NIGHT_END:
        return config.NIGHT_OUTFIT
    if temp_c is None:
        return config.DEFAULT_OUTFIT
    if condition == "Rain":
        if temp_c >= config.RAIN_TEMP_HOT:
            return "夏装"
        if temp_c < config.RAIN_TEMP_COLD:
            return "冬装"
        return "秋装"
    if temp_c >= config.TEMP_HOT:
        return "夏装"
    if temp_c <= config.TEMP_COLD:
        return "冬装"
    return "秋装"


def tag_of(filename):
    """从文件名提取特殊表情标签（sad/smile/worry/...），无标签返回 None。"""
    low = filename.lower()
    for tag in config.EMOTION_TAGS:
        if tag in low:
            return tag
    return None


class SpriteLibrary(QObject):
    """装扮 -> 分组 -> 图片条目 的三级图库，负责随机取图。"""

    image_changed = Signal()   # 当前展示图片变化（无参数，外部读取 current_pixmap）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._outfits = {}     # outfit -> {group: [(pixmap, tag), ...]}
        self._outfit = None    # 当前装扮（随机换图在其内部进行）
        self._display = None   # 当前展示位置 (outfit, group, index)

    # ------------------------------------------------------------------ 加载
    @staticmethod
    def _load(path):
        pm = QPixmap(path)
        if pm.isNull():
            return pm
        if config.SPRITE_SCALE < 1.0:
            w = max(1, round(pm.width() * config.SPRITE_SCALE))
            h = max(1, round(pm.height() * config.SPRITE_SCALE))
            pm = pm.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return SpriteLibrary._apply_edge_fade(pm)

    @staticmethod
    def _apply_edge_fade(pixmap):
        """底部 + 右侧羽化遮罩（issue: 桌宠突兀问题 / 底边残影亮线）。

        - 直接对整张画布 (0,0,w,h) 填充渐变，用百分比停靠点控制起止位置，
          不再用 int() 截断坐标，杜绝 Off-by-One 残影亮线；
        - 完全透明点提前到 98% 处结束，保证底边/右边最后 2% 像素绝对透明；
        - 垂直渐变消除半身像底边刀切感；水平渐变消除右侧双马尾发梢的
          垂直刀切边。
        """
        if pixmap.isNull() or (config.FADE_RATIO <= 0
                               and config.RIGHT_FADE_RATIO <= 0):
            return pixmap
        result = QPixmap(pixmap.size())
        result.fill(Qt.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawPixmap(0, 0, pixmap)
        painter.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        w, h = pixmap.width(), pixmap.height()

        if config.FADE_RATIO > 0:
            vgrad = QLinearGradient(QPointF(0, 0), QPointF(0, h))
            vgrad.setColorAt(0.0, QColor(0, 0, 0, 255))
            vgrad.setColorAt(max(0.0, 1.0 - config.FADE_RATIO),
                             QColor(0, 0, 0, 255))
            vgrad.setColorAt(0.98, QColor(0, 0, 0, 0))   # 提前 2% 全透明
            painter.fillRect(0, 0, w, h, vgrad)

        if config.RIGHT_FADE_RATIO > 0:
            hgrad = QLinearGradient(QPointF(0, 0), QPointF(w, 0))
            hgrad.setColorAt(0.0, QColor(0, 0, 0, 255))
            hgrad.setColorAt(max(0.0, 1.0 - config.RIGHT_FADE_RATIO),
                             QColor(0, 0, 0, 255))
            hgrad.setColorAt(0.98, QColor(0, 0, 0, 0))
            painter.fillRect(0, 0, w, h, hgrad)

        painter.end()
        return result

    def preload(self):
        """扫描并预加载 config.OUTFITS 清单中的装扮分组。"""
        for outfit in config.OUTFITS:
            outfit_dir = os.path.join(config.RESOURCE_DIR, outfit)
            if not os.path.isdir(outfit_dir):
                continue
            groups = {}
            for group in sorted(os.listdir(outfit_dir)):
                group_dir = os.path.join(outfit_dir, group)
                if not os.path.isdir(group_dir):
                    continue
                entries = []
                for name in sorted(os.listdir(group_dir)):
                    if name.lower().endswith(".png"):
                        pm = self._load(os.path.join(group_dir, name))
                        if not pm.isNull():
                            entries.append((pm, tag_of(name)))
                if entries:
                    groups[group] = entries
            if groups:
                self._outfits[outfit] = groups
        return len(self._outfits)

    # ------------------------------------------------------------------ API
    def available_outfits(self):
        return sorted(self._outfits)

    @property
    def current_outfit(self):
        return self._outfit

    @property
    def current_pixmap(self):
        if self._display is None:
            return QPixmap()
        outfit, group, index = self._display
        return self._outfits[outfit][group][index][0]

    @property
    def current_tag(self):
        """当前展示图片的表情标签（无则 None）。"""
        if self._display is None:
            return None
        outfit, group, index = self._display
        return self._outfits[outfit][group][index][1]

    def set_outfit(self, outfit):
        """切换装扮；目标不存在时回退默认装扮，再不行用任一可用装扮。"""
        target = outfit if outfit in self._outfits else config.DEFAULT_OUTFIT
        if target not in self._outfits:
            avail = self.available_outfits()
            if not avail:
                return False
            target = avail[0]
        self._outfit = target
        return True

    def pick_random(self):
        """当前装扮下随机分组 + 随机图片。返回该图表情标签（无则 None）。"""
        if self._outfit is None:
            return None
        group = random.choice(list(self._outfits[self._outfit]))
        entries = self._outfits[self._outfit][group]
        index = random.randrange(len(entries))
        self._display = (self._outfit, group, index)
        self.image_changed.emit()
        return entries[index][1]

    def pick_same_group(self):
        """双击：在当前分组（数字目录）内切换到另一张图。

        保持分组不变，随机换一张不同的图；分组只有一张图时返回 False。
        """
        if self._display is None:
            return False
        outfit, group, index = self._display
        entries = self._outfits[outfit][group]
        if len(entries) < 2:
            return False
        new_index = random.randrange(len(entries) - 1)
        if new_index >= index:
            new_index += 1
        self._display = (outfit, group, new_index)
        self.image_changed.emit()
        return True

    def pick_emotion(self, tag):
        """按情绪词找图（issue: 对话与PNG不对应）。搜索顺序：

        1. 当前数字文件目录（当前展示图所在分组）；
        2. 当前装扮文件夹（其余分组）；
        3. 都没有 -> 返回 False，保持当前图片不变（直接结束）。
        """
        if tag is None or self._outfit is None:
            return False
        # 1. 当前数字目录
        cur_group = None
        if self._display is not None:
            outfit, cur_group, index = self._display
            matches = [i for i, (_, t) in enumerate(self._outfits[outfit][cur_group])
                       if t == tag]
            if matches:
                new_index = random.choice(matches)
                if new_index != index:
                    self._display = (outfit, cur_group, new_index)
                    self.image_changed.emit()
                return True
        # 2. 当前装扮文件夹内（其他分组）
        found = [(group, i)
                 for group, entries in self._outfits[self._outfit].items()
                 if group != cur_group
                 for i, (_, t) in enumerate(entries) if t == tag]
        if found:
            group, index = random.choice(found)
            self._display = (self._outfit, group, index)
            self.image_changed.emit()
            return True
        return False

    def pick_by_tag(self, tag):
        """按情绪标签取图：优先当前装扮，找不到再全装扮兜底。

        仅切换展示图（不改变装扮），下一次 pick_random 会回到装扮内的随机图。
        找不到对应标签的图片时返回 False，保持当前图不变。
        """
        if tag is None or self._outfit is None:
            return False
        outfits = (self._outfit,) + tuple(
            o for o in self.available_outfits() if o != self._outfit)
        for outfit in outfits:
            matches = [(group, index)
                       for group, entries in self._outfits[outfit].items()
                       for index, (_, t) in enumerate(entries) if t == tag]
            if matches:
                group, index = random.choice(matches)
                self._display = (outfit, group, index)
                self.image_changed.emit()
                return True
        return False
