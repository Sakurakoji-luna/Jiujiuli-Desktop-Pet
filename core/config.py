# -*- coding: utf-8 -*-
"""全局配置：路径、装扮选择规则、语料路由时段、定时参数。

所有可调参数集中在此文件，改动后重启程序即可生效。
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOURCE_DIR = os.path.join(BASE_DIR, "resource")
DATA_DIR = os.path.join(BASE_DIR, "data")
DIALOGUES_PATH = os.path.join(DATA_DIR, "dialogues.json")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")

os.makedirs(DATA_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# 装扮（resource 下的文件夹）：每个装扮下按 1,2,3... 子文件夹分组，
# 同组 PNG 动作连贯（并非表情分类）。resource 下其余文件夹（如 其他/）
# 存放 UI 素材，不在装扮清单内。
# ---------------------------------------------------------------------------
OUTFITS = ["夏装", "冬装", "秋装", "家居"]
DEFAULT_OUTFIT = "夏装"

# 深夜（22:00 ~ 次日 6:00）无视温度与天气，强制使用家居装扮
NIGHT_OUTFIT = "家居"
NIGHT_START, NIGHT_END = 22, 6

# 温度（°C）与天气决定装扮的阈值
TEMP_HOT = 26          # 温度 >= 该值穿夏装
TEMP_COLD = 12         # 温度 <= 该值穿冬装
RAIN_TEMP_HOT = 28     # 雨天：温度 >= 该值仍穿夏装
RAIN_TEMP_COLD = 18    # 雨天：温度 < 该值穿冬装

# ---------------------------------------------------------------------------
# 图片与交互
# ---------------------------------------------------------------------------
SPRITE_SCALE = 2 / 3             # 素材整体缩放比例（1.0 = 原大小）
PICK_INTERVAL_MS = 60 * 1000     # 随机换图周期（文档要求 1min）
BUBBLE_DURATION_MS = 5000        # 气泡显示时长（毫秒）
CHAT_BUBBLE_DURATION_MS = 8000   # AI 回复气泡时长（毫秒）
DRAG_THRESHOLD = 6               # 按下移动小于该像素数视为“点击”
OLD_MAID_AI_DELAY_MS = 900       # 抽鬼牌：玖玖里回合的思考延迟
# 抽鬼牌：悬停玖玖里的牌触发互动台词（鬼牌台词有微妙变化）
OLD_MAID_HOVER_CHANCE = 0.5        # 普通牌悬停触发概率
OLD_MAID_HOVER_JOKER_CHANCE = 0.8  # 鬼牌悬停触发概率
OLD_MAID_HOVER_COOLDOWN_MS = 2500  # 悬停台词冷却（毫秒）
CONCENTRATION_PAIRS = 8          # 神经衰弱：牌对数（8 对 = 4x4 棋盘）
CONCENTRATION_DEFAULT_DIFFICULTY = "认真"
# 已知牌数超过阈值后，每回合开始玖玖里随机遗忘部分已知位置
CONCENTRATION_FORGET_THRESHOLD = 12
CONCENTRATION_FORGET_RATE = {"全力": 0.0, "认真": 0.1, "休闲": 0.3}

# 活跃模式：超时后随机位置散步+台词；关闭则超时后隐藏
ACTIVE_MODE_DEFAULT = True
IDLE_TIMEOUT = 10 * 60           # 秒：无操作判定超时
IDLE_CHECK_INTERVAL = 30 * 1000  # 毫秒：超时检查周期

# 系统托盘图标与扑克牌素材
TRAY_ICON_PATH = os.path.join(RESOURCE_DIR, "夏装", "1", "default.png")
CARD_DIR = os.path.join(RESOURCE_DIR, "其他", "扑克牌", "png")
FADE_RATIO = 0.25                # 底部渐隐羽化比例（0 = 关闭），消除半身像“刀切”底边
RIGHT_FADE_RATIO = 0.08          # 右侧渐隐羽化比例（0 = 关闭），消除双马尾发梢垂直刀切边

# 特殊表情标签：文件名含这些词的图片触发台词气泡（文档：sad/smile/worry/serious/meditation）
EMOTION_TAGS = ["sad", "smile", "worry", "serious", "meditation", "shy", "angry"]

# ---------------------------------------------------------------------------
# 语料路由时段（小时区间，含起点不含终点；late_night 跨零点）
# ---------------------------------------------------------------------------
PERIODS = {
    "late_night": (22, 6),
    "morning": (6, 9),
    "daytime": (9, 17),
    "evening": (17, 22),
}

# ---------------------------------------------------------------------------
# 天气采集（wttr.in，无需 API Key）
# ---------------------------------------------------------------------------
WTTR_URL = "https://wttr.in/?format=j1"
WEATHER_CITY = ""             # 留空 = 按 IP 自动定位；可填城市名，如 "Beijing"
WEATHER_POLL_INTERVAL = 20 * 60   # 秒。文档要求 15~30 分钟一次
WEATHER_TIMEOUT = 8               # 单次请求超时（秒）

# ---------------------------------------------------------------------------
# AI API 接入（OpenAI 兼容接口，如 DeepSeek）
# ---------------------------------------------------------------------------
API_DEFAULT_BASE = "https://api.deepseek.com"
API_DEFAULT_MODEL = "deepseek-chat"
API_TIMEOUT = 30              # API 请求超时（秒）
API_TEMPERATURE = 0.8         # 生成温度：太低机械、太高容易漏情绪标签
API_MAX_TOKENS = 512          # 回复上限（气泡台词 1~3 句话，无需太长）

# ---------------------------------------------------------------------------
# 酒馆模式提示词引擎（角色卡 + 世界书 + 滑动窗口历史 + 后置指令）
# ---------------------------------------------------------------------------
CHAR_CARD_PATH = os.path.join(DATA_DIR, "kukuri_card.json")
CHAT_HISTORY_PATH = os.path.join(DATA_DIR, "chat_history.json")
CHAT_MAX_HISTORY = 8          # 滑动窗口保留的消息条数（约 4 轮对话）
