# -*- coding: utf-8 -*-
"""环境数据采集器：wttr.in 低频轮询 + 全局缓存。

- 无需任何 API Key：直接 GET wttr.in 的 JSON 接口。
- 后台守护线程每隔 WEATHER_POLL_INTERVAL 秒拉取一次，结果缓存为全局变量，
  供装扮选择与语料路由读取；单次请求带超时，网络异常时保留上次结果。
- 每次成功拉取会在控制台打印当前系统小时数、天气状态标志与温度。
"""
import datetime
import logging
import threading

import requests

from core import config

log = logging.getLogger("DesktopSprite.weather")

# 天气描述关键字 -> 项目内部状态标志（顺序即优先级）
_COND_MAP = [
    ("thunder", "Rain"),
    ("rain", "Rain"),
    ("drizzle", "Rain"),
    ("shower", "Rain"),
    ("snow", "Snow"),
    ("sleet", "Snow"),
    ("ice", "Snow"),
    ("clear", "Sunny"),
    ("sunny", "Sunny"),
    ("cloud", "Cloudy"),
    ("overcast", "Cloudy"),
    ("mist", "Cloudy"),
    ("fog", "Cloudy"),
    ("haze", "Cloudy"),
]

# 全局缓存：主线程只读，天气线程负责写
_cache = {"condition": "Unknown", "raw": "", "temp_c": None, "updated": None}


def normalize_condition(desc):
    """把 wttr.in 的天气描述文本归一到内部状态标志。"""
    if not desc:
        return "Unknown"
    low = desc.lower()
    for key, flag in _COND_MAP:
        if key in low:
            return flag
    return "Unknown"


def fetch_weather():
    """拉取一次天气并写入缓存。成功返回 True。"""
    if config.WEATHER_CITY:
        url = "https://wttr.in/{}?format=j1".format(config.WEATHER_CITY)
    else:
        url = config.WTTR_URL
    resp = requests.get(url, timeout=config.WEATHER_TIMEOUT,
                        headers={"User-Agent": "curl/8.0"})
    resp.raise_for_status()
    data = resp.json()
    cur = data["current_condition"][0]
    desc = cur["weatherDesc"][0]["value"]
    try:
        temp = float(cur.get("temp_C"))
    except (TypeError, ValueError):
        temp = None
    _cache["condition"] = normalize_condition(desc)
    _cache["raw"] = desc
    _cache["temp_c"] = temp
    _cache["updated"] = datetime.datetime.now()
    hour = datetime.datetime.now().hour
    print(f"[Weather] 系统小时: {hour:02d} | 天气: {_cache['condition']} "
          f"({_cache['raw']}) | 温度: {_cache['temp_c']}°C")
    return True


def _poll_loop(stop_event):
    """后台轮询线程：立即拉一次，之后每隔固定间隔拉取。"""
    while not stop_event.is_set():
        try:
            fetch_weather()
        except Exception as exc:  # 网络异常不致命，保留缓存旧值
            log.warning("天气拉取失败: %s", exc)
        stop_event.wait(config.WEATHER_POLL_INTERVAL)


class WeatherCollector:
    """后台天气采集器：start() 启动守护线程，stop() 通知退出。"""

    def __init__(self):
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=_poll_loop, args=(self._stop,),
            daemon=True, name="weather-collector")

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    @staticmethod
    def get_condition():
        """缓存的天气状态标志（Sunny/Rain/Cloudy/Snow/Unknown）。"""
        return _cache["condition"]

    @staticmethod
    def get_temp():
        """缓存的温度（°C，float；无数据时为 None）。"""
        return _cache["temp_c"]
