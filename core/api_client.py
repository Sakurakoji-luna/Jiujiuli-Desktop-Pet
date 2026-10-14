# -*- coding: utf-8 -*-
"""AI API 客户端：OpenAI 兼容 chat/completions 接口（如 DeepSeek）。

- 配置（base_url / api_key / model / verified）持久化在 data/settings.json。
- test()：用一条最小请求检测用户填写的网址与 Key 是否可用；
  兼容 "https://host"、"https://host/v1"、"https://host/.../chat/completions"
  三种写法，自动尝试 /chat/completions 与 /v1/chat/completions。
- chat()：发送一条消息并返回 AI 回复文本，失败抛异常。
"""
import requests

from core import config, settings


class ApiClient:
    def __init__(self):
        self.base_url = config.API_DEFAULT_BASE
        self.api_key = ""
        self.model = config.API_DEFAULT_MODEL
        self.verified = False
        self._endpoint = None   # 检测通过的接口地址
        self._load()

    # ------------------------------------------------------------ 配置持久化
    def _load(self):
        data = settings.load_settings().get("api", {})
        self.base_url = data.get("base_url", config.API_DEFAULT_BASE)
        self.api_key = data.get("api_key", "")
        self.model = data.get("model", config.API_DEFAULT_MODEL)
        self.verified = bool(data.get("verified", False))

    def save(self):
        data = settings.load_settings()
        data["api"] = {"base_url": self.base_url,
                       "api_key": self.api_key,
                       "model": self.model,
                       "verified": self.verified}
        settings.save_settings(data)

    @property
    def is_connected(self):
        return bool(self.verified and self.base_url and self.api_key)

    # ---------------------------------------------------------------- 请求
    @staticmethod
    def _resolve_endpoint(base_url):
        """按用户写法推算出候选接口地址列表。"""
        url = base_url.strip().rstrip("/")
        if url.endswith("/chat/completions"):
            return [url]
        if url.endswith("/v1"):
            return [url + "/chat/completions"]
        return [url + "/chat/completions", url + "/v1/chat/completions"]

    def _post(self, endpoint, messages, max_tokens, temperature=None):
        body = {"model": self.model, "messages": messages,
                "max_tokens": max_tokens}
        if temperature is not None:
            body["temperature"] = temperature
        return requests.post(
            endpoint, json=body,
            headers={"Authorization": "Bearer " + self.api_key},
            timeout=config.API_TIMEOUT)

    def test(self, base_url, api_key, model):
        """检测网址与 Key 是否可用，返回 (ok, message)。"""
        if not base_url.startswith(("http://", "https://")):
            return False, "API 地址需以 http:// 或 https:// 开头"
        if not api_key:
            return False, "API Key 不能为空"
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        for endpoint in self._resolve_endpoint(base_url):
            try:
                resp = self._post(endpoint,
                                  [{"role": "user", "content": "ping"}],
                                  max_tokens=1)
            except requests.RequestException as exc:
                return False, f"请求失败: {exc}"
            if resp.status_code == 200:
                self._endpoint = endpoint
                return True, "连接成功，接口可用"
            if resp.status_code in (401, 403):
                return False, f"鉴权失败 (HTTP {resp.status_code})，请检查 Key"
            if resp.status_code == 404:
                continue   # 该地址不对，试下一个候选
            return False, f"HTTP {resp.status_code}: {resp.text[:120]}"
        return False, "未找到可用的 chat/completions 接口，请检查地址"

    def chat_messages(self, messages):
        """发送组装好的 messages 列表，返回 AI 回复文本；失败抛异常。"""
        if not self.is_connected:
            raise RuntimeError("未连接")
        endpoint = self._endpoint or self._resolve_endpoint(self.base_url)[0]
        resp = self._post(endpoint, messages,
                          max_tokens=config.API_MAX_TOKENS,
                          temperature=config.API_TEMPERATURE)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
