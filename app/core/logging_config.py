"""统一日志：写文件 + 控制台，并过滤敏感串（密码、Token、Cookie）。"""

import logging
import os
import re
import sys
from datetime import datetime

from .paths import LOG_DIR

_SECRET_PATTERNS = [
    (re.compile(r"(ghp_[A-Za-z0-9]{8,})"), "ghp_***"),
    (re.compile(r"(Authorization[\"']?\s*[:=]\s*)([A-Za-z0-9._\-]+)", re.I), r"\1***"),
    (re.compile(r"(\"password\"\s*:\s*\")([^\"]+)\"", re.I), r"\1***\""),
    (re.compile(r"(\"app_secret\"\s*:\s*\")([^\"]+)\"", re.I), r"\1***\""),
    (re.compile(r"(cookie[\"']?\s*[:=]\s*)([^\s,;]+)", re.I), r"\1***"),
]


class SecretFilter(logging.Filter):
    """避免任何一行日志把凭证打出来。"""

    def filter(self, record):
        try:
            msg = record.getMessage()
        except Exception:
            return True
        for pattern, repl in _SECRET_PATTERNS:
            msg = pattern.sub(repl, msg)
        record.msg = msg
        record.args = ()
        return True


_CONFIGURED = {}


def setup_logging(name="app", level=logging.INFO):
    """初始化并返回 logger；重复调用返回同一个实例，不会重复加 handler。"""
    if name in _CONFIGURED:
        return _CONFIGURED[name]

    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    file_path = os.path.join(LOG_DIR, "%s_%s.log" % (name, datetime.now().strftime("%Y%m%d")))
    fh = logging.FileHandler(file_path, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.addFilter(SecretFilter())

    sh = logging.StreamHandler(stream=sys.stdout)
    sh.setFormatter(fmt)
    sh.addFilter(SecretFilter())

    logger.addHandler(fh)
    logger.addHandler(sh)
    _CONFIGURED[name] = logger
    return logger
