"""核心公共模块：配置、路径、日志、异常。"""

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
    EXCEL_DIR,
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
    "BASE_DIR", "CONFIG_DIR", "OUTPUT_DIR", "EXCEL_DIR", "RAW_DIR", "LOG_DIR", "DIST_DIR",
    "DOCS_DIR", "DATA_JSON", "FULL_JSON", "INDEX_HTML",
]
