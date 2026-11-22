"""核心公共模块：配置、路径、日志、异常。"""

import os

# Windows 上 Python 默认不读系统根证书，urllib 访问 api.github.com 会报
# CERTIFICATE_VERIFY_FAILED；这里统一指向 certifi 的 CA 包，缺 certifi 就保持默认。
try:
    import certifi as _certifi

    os.environ.setdefault("SSL_CERT_FILE", _certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", _certifi.where())
except Exception:  # pragma: no cover - 没装 certifi 时不影响其它功能
    pass

from .config import load_config, load_credentials, require_credentials, mask, scrub, validate_config
from .exceptions import (
    ConfigError,
    CrawlError,
    DataValidationError,
    JbufaError,
    LoginError,
    PublishBlocked,
)
from .logging_config import setup_logging
from .paths import (
    BASE_DIR,
    CONFIG_DIR,
    DATA_JSON,
    DIST_DIR,
    DOCS_DIR,
    FULL_JSON,
    INDEX_HTML,
    LOG_DIR,
    OUTPUT_DIR,
    RAW_DIR,
    ensure_dirs,
)

__all__ = [
    "load_config", "load_credentials", "require_credentials", "mask", "scrub", "validate_config",
    "JbufaError", "ConfigError", "LoginError", "CrawlError", "DataValidationError", "PublishBlocked",
    "setup_logging", "ensure_dirs",
    "BASE_DIR", "CONFIG_DIR", "OUTPUT_DIR", "RAW_DIR", "LOG_DIR", "DIST_DIR",
    "DOCS_DIR", "DATA_JSON", "FULL_JSON", "INDEX_HTML",
]
