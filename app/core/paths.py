"""统一的路径定义。所有模块都从这里取目录，避免各处拼字符串导致换电脑后跑不动。"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONFIG_DIR = os.path.join(BASE_DIR, "config")
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
RAW_DIR = os.path.join(OUTPUT_DIR, "raw")
LOG_DIR = os.path.join(OUTPUT_DIR, "logs")
BACKUP_DIR = os.path.join(OUTPUT_DIR, "backups")
DIST_DIR = os.path.join(BASE_DIR, "dist")
DOCS_DIR = os.path.join(BASE_DIR, "docs")
PRIVATE_DIR = os.path.join(BASE_DIR, "private")          # 合同财务等受控数据，绝不发布
CONTRACTS_JSON = os.path.join(PRIVATE_DIR, "contracts.json")

CONFIG_JSON = os.path.join(CONFIG_DIR, "config.json")
CONFIG_EXAMPLE = os.path.join(CONFIG_DIR, "config.example.json")
CREDENTIALS_JSON = os.path.join(CONFIG_DIR, "credentials.json")
PUBLIC_FIELDS_JSON = os.path.join(CONFIG_DIR, "public_fields.json")
PUBLIC_FIELDS_EXAMPLE = os.path.join(CONFIG_DIR, "public_fields.example.json")

DATA_JSON = os.path.join(BASE_DIR, "data.json")          # 公开（脱敏）数据，进仓库
FULL_JSON = os.path.join(OUTPUT_DIR, "data.full.json")   # 完整数据，仅本地，绝不入库
INDEX_HTML = os.path.join(BASE_DIR, "index.html")
COORDS_JSON = os.path.join(DATA_DIR, "coords.json")
MAP_TEMPLATE = os.path.join(BASE_DIR, "app", "map_template.html")


def ensure_dirs():
    """创建运行时需要的目录（已存在就跳过）。"""
    for d in (OUTPUT_DIR, RAW_DIR, LOG_DIR, BACKUP_DIR, DIST_DIR):
        os.makedirs(d, exist_ok=True)
