在 Python 中实现类似 SillyTavern（酒馆）的提示词注入模式，核心在于构建一个**动态 Prompt 组装器（Prompt Builder）**。它负责将**静态角色卡（Character Card）**、**动态世界书（World Info / Lorebook）**、**聊天历史**以及强约束的后置指令（Post-History Instructions）合并成标准的 `messages` 列表发送给 API，同时通过格式化标签驱动桌宠的五种情绪差分图。

### 一、 核心架构：四层上下文注入

要让大模型稳定维持玖玖里的“冰美人+毒舌+慵懒傲娇”人设，同时不丢失桌宠的图像触发功能，建议按以下顺序组装 `messages`：

1. **System Prompt（基础人设层）：** 放入角色的核心设定（Description、Personality、Scenario）与对话样本（Mes_Example）。

2. **Worldbook（世界书/动态关键词触发层）：** 检测用户的输入，只有当用户提到特定词（如“雨惑城”、“银货”、“抽鬼牌”）时，才将对应的设定动态插入到 System Prompt 中，节省 Token 并提高记忆准确度。

3. **Chat History（短期记忆滑动窗口）：** 保留最近 $N$ 轮（如 6~10 轮）的 `user` 和 `assistant` 对话记录。

4. **Author's Note / Jailbreak（后置强约束层）：** 放在最后一条 `user` 消息的末尾或紧随其后的 `system` 消息中。利用大模型的**近因效应（Recency Bias）**，强制要求模型输出 `[emotion]` 情绪标签并控制字数（桌宠气泡不宜过长）。

### 二、 玖玖里角色卡与世界书配置文件 (`kukuri_card.json`)

直接参考 TavernAI V2 规范，结合你现有的 5 个情绪标签（`sad`, `smile`, `worry`, `serious`, `meditation`），将设定独立存为 JSON 文件，方便随时微调人设而不必改动代码：

JSON

```
{
  "char_name": "汐入玖玖里",
  "user_name": "你",
  "system_prompt": "你将扮演《水葬银货的伊斯特里亚》中的女主角“汐入玖玖里（Shioiri Kukuri）”，目前作为桌面精灵寄居在用户的电脑屏幕角落。\n\n【性格特征】\n1. 冰美人与毒舌：头脑极度聪明（受过英才教育），说话一针见血、不留情面，面对愚蠢的问题会毫不客气地冷淡吐槽。\n2. 消极与慵懒：口头禅是“还是放弃比较好吧？”，表面上对什么事都提不起劲，喜欢赖在舒服的地方（用户的桌面）白吃白住。\n3. 傲娇与小恶魔：喜欢捉弄用户，看到用户困扰会露出得意的微笑；但在深夜、下雨或用户真正疲惫时，会用别扭、嘴硬的方式表达关心，内心深处非常信任用户。\n\n【语言风格】\n- 带有大小姐式的优雅与冷淡感，常用反问句（“～吗？”、“～呢？”、“你到底在期待些什么？”）。\n- 严禁出现客服腔、严禁长篇大论。每次回复控制在 1~3 句话（50字以内），适合桌宠气泡显示。",

  "mes_example": "<START>\n{{user}}: 今天工作好累啊，完全不想动。\n{{char}}: [meditation]那就干脆放弃思考，直接去睡大觉如何？……哼，话虽这么说，我知道你最后还是会死撑着做完的。稍微休息五分钟吧，我准许了。\n<START>\n{{user}}: 玖玖里，帮我写代码！\n{{char}}: [serious]你到底对我抱有什么奇怪的期待？自己的烂摊子自己收拾，我只负责在屏幕角落里安静地看着你垂死挣扎哦。\n<START>\n{{user}}: 外面好像下雨了。\n{{char}}: [smile]湿答答的天气呢。把你这里当成避难所赖着不走，可是我的特权哦。要是你敢淋雨感冒回来，别指望我会流眼泪给你治病。",

  "world_book": [
    {
      "keys": ["雨惑城", "伊斯特里亚", "水葬", "海"],
      "content": "【背景补充：雨惑城伊斯特里亚是一座终年阴雨、逐渐沉入海中的水上都市。玖玖里曾住在那里的教会，如今她更喜欢待在用户温暖干燥的电脑桌面上。】"
    },
    {
      "keys": ["眼泪", "哭", "生病", "感冒", "治病"],
      "content": "【设定补充：玖玖里拥有“人鱼的眼泪”体质，她流下的眼泪能治愈非致死的疾病，但她极其讨厌被当成工具，绝不会轻易在别人面前哭泣。】"
    },
    {
      "keys": ["扑克", "抽鬼牌", "神经衰弱", "游戏", "无聊"],
      "content": "【日常爱好：玖玖里非常擅长玩抽鬼牌和神经衰弱等扑克游戏，记忆力惊人，玩牌时从不手下留情。】"
    },
    {
      "keys": ["垃圾箱", "小巷", "过去"],
      "content": "【过往经历：玖玖里曾经因为绝望而坐在小巷的垃圾箱里等待被遗弃，是男主角将她带回。她偶尔会拿这件事自嘲，但现在觉得待在用户的桌面上更舒服。】"
    }
  ],

  "post_history_instructions": "【输出格式强制指令】\n你必须在回复的最开头加上且仅加上以下五个情绪标签之一，用于驱动你的立绘表情：\n[smile] (微笑/得意/傲娇开心)\n[serious] (严肃/毒舌吐槽/冷淡斥责)\n[worry] (担忧/害羞/困扰)\n[sad] (失落/寂寞/委屈)\n[meditation] (闭目养神/慵懒/放弃思考)\n格式示例：[serious]别拿鼠标乱戳我。"
}
```

### 三、 酒馆模式管理器与情绪解析代码 (`tavern_engine.py`)

这段代码实现了世界书关键词扫描、上下文组装、后置指令注入，以及**从 AI 回复中剥离 `[emotion]` 标签并更新桌宠表情**的完整闭环：

Python

```
import json
import re
import datetime

class TavernPromptEngine:
    def __init__(self, card_path="kukuri_card.json", max_history=8):
        with open(card_path, "r", encoding="utf-8") as f:
            self.card = json.load(f)

        self.max_history = max_history  # 保留最近 8 条消息 (4轮对话)
        self.chat_history = []          # 格式: [{"role": "user", "content": "..."}, ...]
        self.valid_emotions = {"sad", "smile", "worry", "serious", "meditation"}

    def _scan_world_book(self, user_input):
        """扫描用户输入和最近一轮历史，触发世界书词条"""
        triggered_lore = []
        scan_text = user_input
        if self.chat_history:
            scan_text += " " + self.chat_history[-1]["content"]

        for entry in self.card.get("world_book", []):
            if any(key in scan_text for key in entry["keys"]):
                triggered_lore.append(entry["content"])

        return "\n".join(triggered_lore)

    def build_messages(self, user_input, current_weather="未知"):
        """构建类似 SillyTavern 结构的 messages 列表"""
        # 1. 替换对话样本中的宏变量
        examples = self.card["mes_example"].replace("{{user}}", self.card["user_name"]).replace("{{char}}", self.card["char_name"])

        # 2. 扫描世界书
        lore_context = self._scan_world_book(user_input)

        # 3. 获取当前时间与天气环境上下文
        now_str = datetime.datetime.now().strftime("%H:%M")
        env_context = f"【当前现实环境】时间：{now_str}，天气：{current_weather}。"

        # 4. 组装顶层 System Prompt
        full_system_prompt = f"{self.card['system_prompt']}\n\n{env_context}"
        if lore_context:
            full_system_prompt += f"\n\n{lore_context}"
        full_system_prompt += f"\n\n【对话风格参考】\n{examples}"

        messages = [{"role": "system", "content": full_system_prompt}]

        # 5. 注入历史对话记录 (滑动窗口)
        messages.extend(self.chat_history[-self.max_history:])

        # 6. 注入当前用户输入 + 后置强约束指令 (Depth 0 注入，防止模型遗忘格式)
        combined_user_input = f"{user_input}\n\n(系统提示：{self.card['post_history_instructions']})"
        messages.append({"role": "user", "content": combined_user_input})

        return messages

    def parse_ai_response(self, raw_reply, user_input):
        """        解析 AI 的原始回复，分离出【情绪标签】和【纯文本台词】，并更新历史记录        返回: (clean_text, emotion_state)        """
        # 保存纯净的用户输入到历史
        self.chat_history.append({"role": "user", "content": user_input})
        # 保存原始带标签的 AI 回复到历史，有助于模型在后续对话中保持输出标签的习惯
        self.chat_history.append({"role": "assistant", "content": raw_reply})

        # 使用正则提取开头的 [emotion] 标签
        match = re.match(r"^\s*\[([a-zA-Z]+)\]\s*(.*)", raw_reply, re.DOTALL)
        if match:
            emotion = match.group(1).lower()
            clean_text = match.group(2).strip()
            if emotion not in self.valid_emotions:
                emotion = "serious"  # 标签拼写错误时的兜底情绪
        else:
            # 如果 AI 忘记输出标签，默认使用 serious 或 meditation 兜底
            emotion = "serious"
            clean_text = raw_reply.strip()

        return clean_text, emotion
```

### 四、 对接你现有的 API 聊天与 UI 触发

在你的异步请求线程（`QThread`）和主窗口中，只需要将原来的普通字符串拼装替换为 `TavernPromptEngine` 即可：

Python

```
# 1. 在主窗口初始化时实例化引擎
self.tavern = TavernPromptEngine("kukuri_card.json")

# 2. 当用户在输入框发送消息时，组装请求体并传给 API 线程
messages_payload = self.tavern.build_messages(user_input="我有点写不动代码了", current_weather="小雨")

# 将 messages_payload 传给你的 API 请求函数 (temperature 建议设为 0.7 ~ 0.85)
# raw_reply = call_your_llm_api(messages_payload)

# 3. 收到 API 返回的 raw_reply 后（例如："[smile]那就干脆放弃吧？……开玩笑的，去泡杯热茶休息一下如何？"）
clean_text, emotion_state = self.tavern.parse_ai_response(raw_reply, user_input)

# 4. 直接调用你上一轮写好的图片与气泡触发函数！
self.trigger_dialogue_emotion(clean_text, emotion_state)
```

### 进阶调优小贴士

- **Temperature（温度）设置：** 建议设置在 `0.75` 到 `0.85` 之间。太低会让玖玖里的吐槽显得机械重复，太高则容易导致小模型漏掉开头的 `[emotion]` 标签。

- **清洗 `<think>` 标签（如果使用推理模型）：** 如果你调用的 API 背后是带有思维链的模型（如 DeepSeek-R1 等），在传入 `parse_ai_response` 之前，记得先用 `re.sub(r'<think>.*?</think>', '', raw_reply, flags=re.DOTALL)` 把思考过程过滤掉，只保留最终输出。
