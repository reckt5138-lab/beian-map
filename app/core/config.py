"""配置读取：环境变量 > 本地敏感配置 > 普通配置 > 安全默认值。

设计约束（V3.0）：
- 敏感值只从环境变量或 config/credentials.json 读，绝不出现在代码/日志/仓库里。
- 缺配置时抛 ConfigError，附带中文说明，不静默用空账号去登录。
"""

import copy
import json
import os

from .exceptions import ConfigError
from .paths import CONFIG_EXAMPLE, CONFIG_JSON, CREDENTIALS_JSON

DEFAULTS = {
    "base_url": "https://c.jbufa.com",
    "login": {"client_id": "web"},
    # 默认直连：Windows 上系统代理（Clash 等）没开时会抛 ProxyError，看起来像登录失败
    "network": {"use_proxy": False},
    "crawl": {
        "tab_types": [100],
        "status_filter": ["备案项目"],
        "page_size": 50,
        "max_pages": 500,
        "request_interval": 0.15,
        "retry": 3,
        "timeout": 60,
        "with_detail": True,
        "with_follow": True,
        "with_client": True,
    },
    "export": {
        "output_dir": "output",
        "file_prefix": "备案项目",
        "keep_days": 60,
        "use_field_template": True,
        "checkin_columns": 50,
        "extra_fields": [],
    },
    "publish": {"github_owner": "", "github_repo": "", "branch": "main"},
}

SENSITIVE_KEYS = ("password", "app_secret", "token", "cookie", "secret")


def _read_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except ValueError as exc:
        raise ConfigError("配置文件格式错误（不是合法 JSON）：%s\n原因：%s" % (path, exc))
    if not isinstance(data, dict):
        raise ConfigError("配置文件顶层必须是 JSON 对象：%s" % path)
    return data


def _deep_merge(base, extra):
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(require_file=False):
    """返回合并后的配置字典。不写盘、不改动原文件。"""
    base = DEFAULTS
    if os.path.exists(CONFIG_EXAMPLE):
        base = _deep_merge(base, _read_json(CONFIG_EXAMPLE))
    if os.path.exists(CONFIG_JSON):
        base = _deep_merge(base, _read_json(CONFIG_JSON))
    elif require_file:
        raise ConfigError(
            "缺少配置文件 config/config.json。\n"
            "请复制 config/config.example.json 为 config/config.json 后填写。\n"
            "（青鸾地图.bat（菜单 1） 会自动做这一步）"
        )

    # 环境变量覆盖（只覆盖有意义的几项）
    env_map = {
        ("login", "username"): "JUFA_USERNAME",
        ("login", "password"): "JUFA_PASSWORD",
        ("base_url",): "JUFA_BASE_URL",
        ("publish", "github_owner"): "GITHUB_OWNER",
        ("publish", "github_repo"): "GITHUB_REPO",
    }
    for path, env in env_map.items():
        val = os.environ.get(env)
        if val:
            node = base
            for key in path[:-1]:
                node = node.setdefault(key, {})
            node[path[-1]] = val

    validate_config(base)
    return base


def load_credentials():
    """账号密码：环境变量优先，其次是 config/credentials.json，最后 config.json 的 login 段。"""
    cred = {}
    if os.path.exists(CREDENTIALS_JSON):
        cred = _read_json(CREDENTIALS_JSON)
    username = os.environ.get("JUFA_USERNAME") or cred.get("username") or ""
    password = os.environ.get("JUFA_PASSWORD") or cred.get("password") or ""
    if not username or not password:
        cfg_login = load_config().get("login") or {}
        username = username or cfg_login.get("username") or ""
        password = password or cfg_login.get("password") or ""
    return {"username": username, "password": password}


def require_credentials():
    cred = load_credentials()
    if not cred["username"] or not cred["password"]:
        raise ConfigError(
            "缺少青鸾账号。请任选一种方式：\n"
            "  1) 在 config/credentials.json 里填 username / password（推荐，不进仓库）\n"
            "  2) 设置环境变量 JUFA_USERNAME / JUFA_PASSWORD\n"
            "  3) 青鸾地图.bat（菜单 1） 会引导你填写"
        )
    return cred


def validate_config(cfg):
    if not isinstance(cfg.get("base_url"), str) or not cfg["base_url"].startswith("http"):
        raise ConfigError("配置项 base_url 必须是 http(s) 地址")
    crawl = cfg.get("crawl") or {}
    for key in ("page_size", "max_pages", "retry", "timeout"):
        val = crawl.get(key)
        if val is not None and (not isinstance(val, int) or val <= 0):
            raise ConfigError("配置项 crawl.%s 必须是正整数，当前：%r" % (key, val))
    export = cfg.get("export") or {}
    if not isinstance(export.get("checkin_columns", 50), int):
        raise ConfigError("配置项 export.checkin_columns 必须是整数")
    return True


def mask(value):
    """日志安全：把密码 / Token / Cookie 变成 ***。"""
    if value is None:
        return ""
    text = str(value)
    if len(text) <= 6:
        return "***"
    return text[:3] + "***" + text[-2:]


def scrub(data):
    """递归清除字典里的敏感键，返回副本（用于打日志 / 诊断报告）。"""
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            if any(s in str(k).lower() for s in SENSITIVE_KEYS):
                out[k] = "***"
            else:
                out[k] = scrub(v)
        return out
    if isinstance(data, list):
        return [scrub(x) for x in data]
    return data
