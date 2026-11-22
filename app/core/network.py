"""网络会话：默认直连，只有 config.network.use_proxy=true 时才走系统代理。

为什么这样做：Windows 上 requests / urllib 会自动读取系统代理（HKCU 里的
ProxyServer，常见是 Clash 的 127.0.0.1:7890）。代理没开或没起好时，所有请求会直接
抛 ProxyError（Unable to connect to proxy），表现为「登录失败 / 连不上 GitHub」，
但其实站点本身可以直连。这里把「是否走代理」变成配置项，默认直连。
"""

import json
import os
import urllib.request

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config", "config.json")


def _read_use_proxy():
    env = os.environ.get("QL_USE_PROXY", "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if env in ("0", "false", "no", "off"):
        return False
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
        return bool((cfg.get("network") or {}).get("use_proxy"))
    except Exception:
        return False


def use_proxy():
    return _read_use_proxy()


def make_session(cfg=None):
    """返回 requests.Session：默认直连，配置开启时代理生效。"""
    import requests

    s = requests.Session()
    s.trust_env = bool((cfg or {}).get("network", {}).get("use_proxy")) if cfg else _read_use_proxy()
    return s


def opener():
    """返回 urllib 的 opener：直连模式忽略系统代理。"""
    if _read_use_proxy():
        return urllib.request.build_opener()
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def urlopen(req, timeout=30):
    return opener().open(req, timeout=timeout)
