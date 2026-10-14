# -*- coding: utf-8 -*-
"""data/settings.json 读写工具（窗口位置、API 配置等持久化）。"""
import json

from core import config


def load_settings(path=None):
    """读取设置文件；不存在或损坏时返回空 dict。"""
    path = path or config.SETTINGS_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data, path=None):
    """整体覆写设置文件（调用方负责合并旧值）。"""
    path = path or config.SETTINGS_PATH
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass
