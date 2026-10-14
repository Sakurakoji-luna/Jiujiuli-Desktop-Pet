# -*- coding: utf-8 -*-
"""语料路由引擎（V2）：时段 x 天气 选池，支持特殊表情过滤。

路由规则：
    1. 按系统小时数映射时段：late_night(22~6) / morning(6~9) /
       daytime(9~17) / evening(17~22)；
    2. 时段内按天气分流：Rain -> rainy，Sunny -> sunny，其余 -> other；
       该时段的语料缺省对应天气键时依次回退 any / other；
    3. 若给出表情标签（特殊图片触发），优先抽取同 emotion_state 的台词；
    4. 最终兜底 random_click 池。
"""
import datetime
import json
import random

from core import config


class DialogueRouter:
    def __init__(self, corpus_path=None):
        path = corpus_path or config.DIALOGUES_PATH
        with open(path, "r", encoding="utf-8") as f:
            self.corpus = json.load(f)

    # ------------------------------------------------------------ 时段与天气
    @staticmethod
    def get_period(hour):
        """小时数 -> 语料时段名。"""
        for period, (start, end) in config.PERIODS.items():
            if start > end:          # 跨零点区间（深夜）
                if hour >= start or hour < end:
                    return period
            elif start <= hour < end:
                return period
        return "daytime"

    @staticmethod
    def _weather_key(condition):
        if condition == "Rain":
            return "rainy"
        if condition == "Sunny":
            return "sunny"
        return "other"

    # ---------------------------------------------------------------- 抽取
    def get_response(self, current_weather, emotion=None, hour=None):
        """返回 (text, emotion_state)。emotion 为表情标签时优先匹配同情绪台词。"""
        if hour is None:
            hour = datetime.datetime.now().hour
        period = self.get_period(hour)
        section = self.corpus.get(period, {})
        pool = (section.get(self._weather_key(current_weather))
                or section.get("any") or section.get("other") or [])
        if emotion:
            tagged = [e for e in pool if e.get("emotion_state") == emotion]
            if tagged:
                pool = tagged
        selected = random.choice(pool) if pool else None
        if selected is None:
            pool = self.corpus.get("random_click", [])
            selected = random.choice(pool) if pool else None
        if selected is None:
            return "……", "idle"
        return selected["text"], selected["emotion_state"]

    def get_pool_line(self, pool_name):
        """从平铺语料池（random_click / drag_drop）随机取一条。"""
        pool = self.corpus.get(pool_name, [])
        if not pool:
            return "……", "idle"
        selected = random.choice(pool)
        return selected["text"], selected["emotion_state"]
