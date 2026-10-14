# -*- coding: utf-8 -*-
"""酒馆模式提示词引擎（SillyTavern 式四层上下文注入）。

组装顺序：
    1. System Prompt：角色卡基础人设 + 当前时间/天气环境 + 世界书触发词条
       + 对话样本；
    2. Chat History：滑动窗口，保留最近 CHAT_MAX_HISTORY 条消息，
       持久化到 data/chat_history.json（重启后仍有短期记忆）；
    3. 后置强约束指令：追加在当前 user 消息末尾，利用近因效应强制模型
       输出 [emotion] 情绪标签并控制字数。
parse_ai_response() 剥离回复开头的情绪标签（过滤推理模型的 <think> 思维链），
返回 (纯文本台词, 情绪标签)，供气泡显示与情绪差分图切换。
"""
import datetime
import json
import os
import re

from core import config

# 天气标志 -> 中文（注入环境上下文用）
WEATHER_CN = {"Sunny": "晴", "Rain": "下雨", "Cloudy": "多云",
              "Snow": "下雪", "Unknown": "未知"}

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)   # 推理模型思维链
_EMOTION_RE = re.compile(r"^\s*\[([A-Za-z]+)\]\s*(.*)", re.DOTALL)


class TavernPromptEngine:
    def __init__(self, card_path=None, history_path=None, max_history=None):
        card_path = card_path or config.CHAR_CARD_PATH
        history_path = history_path or config.CHAT_HISTORY_PATH
        with open(card_path, "r", encoding="utf-8") as f:
            self.card = json.load(f)
        self._history_path = history_path
        self.max_history = max_history or config.CHAT_MAX_HISTORY
        self.chat_history = self._load_history()
        self.valid_emotions = set(config.EMOTION_TAGS)

    # ------------------------------------------------------------ 历史记忆
    def _load_history(self):
        try:
            with open(self._history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [m for m in data if isinstance(m, dict)
                        and "role" in m and "content" in m][-self.max_history:]
        except (OSError, ValueError):
            pass
        return []

    def _save_history(self):
        try:
            os.makedirs(os.path.dirname(self._history_path), exist_ok=True)
            with open(self._history_path, "w", encoding="utf-8") as f:
                json.dump(self.chat_history[-self.max_history:], f,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass

    # ------------------------------------------------------------ 世界书
    def _scan_world_book(self, user_input):
        """扫描用户输入与最近一条历史，命中关键词的词条注入 System。"""
        triggered = []
        scan_text = user_input
        if self.chat_history:
            scan_text += " " + self.chat_history[-1].get("content", "")
        for entry in self.card.get("world_book", []):
            if any(key in scan_text for key in entry["keys"]):
                triggered.append(entry["content"])
        return "\n".join(triggered)

    # ------------------------------------------------------------ 组装
    def build_messages(self, user_input, current_weather="未知"):
        """组装 OpenAI 兼容的 messages 列表。"""
        # 1. 对话样本宏变量替换
        examples = (self.card["mes_example"]
                    .replace("{{user}}", self.card.get("user_name", "用户"))
                    .replace("{{char}}", self.card["char_name"]))

        # 2. 世界书关键词扫描
        lore = self._scan_world_book(user_input)

        # 3. 时间 + 天气环境上下文
        now_str = datetime.datetime.now().strftime("%H:%M")
        env_context = f"【当前现实环境】时间：{now_str}，天气：{current_weather}。"

        # 4. 顶层 System Prompt
        system = f"{self.card['system_prompt']}\n\n{env_context}"
        if lore:
            system += f"\n\n{lore}"
        system += f"\n\n【对话风格参考】\n{examples}"

        # 5. 历史 + 当前输入（后置强约束，Depth 0 注入防遗忘格式）
        messages = [{"role": "system", "content": system}]
        messages.extend(self.chat_history[-self.max_history:])
        messages.append({"role": "user",
                         "content": f"{user_input}\n\n(系统提示："
                                    f"{self.card['post_history_instructions']})"})
        return messages

    # ------------------------------------------------------------ 解析
    def parse_ai_response(self, raw_reply, user_input):
        """剥离情绪标签，返回 (clean_text, emotion_state)；同时更新历史。

        历史中保存原始带标签回复，帮助模型在后续对话保持输出标签的习惯。
        """
        self.chat_history.append({"role": "user", "content": user_input})
        self.chat_history.append({"role": "assistant", "content": raw_reply})
        self.chat_history = self.chat_history[-self.max_history:]
        self._save_history()

        raw_reply = _THINK_RE.sub("", raw_reply)   # 过滤思维链
        match = _EMOTION_RE.match(raw_reply)
        if match and match.group(1).lower() in self.valid_emotions:
            return match.group(2).strip(), match.group(1).lower()
        # 标签缺失或拼写错误 -> 兜底 serious
        return raw_reply.strip(), "serious"
