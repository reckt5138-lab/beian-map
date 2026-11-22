"""地图构建：模板 → index.html，并做一次产物自检。

V3.0 自检点：
- 文件存在、体积正常
- 只请求同目录 ./data.json（不允许再出现 raw.githubusercontent / jsdelivr 数据地址 / 飞书地址）
- 不含明文凭证
"""

import os
import re
import subprocess
import sys

from ..core.paths import BASE_DIR, INDEX_HTML

FORBIDDEN_PATTERNS = [
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"cli_[a-z0-9]{10,}"),
    re.compile(r"\"password\"\s*:\s*\"[^\"]{3,}\""),
    # 旧数据源残留
    re.compile(r"raw\.githubusercontent\.com"),
    re.compile(r"jsdelivr\.net/gh/"),
    re.compile(r"feishu\.cn|spreadsheet_token|jbufa\.com"),
    re.compile(r"window\.EMBEDDED\s*="),
]


def build(from_json="data.json", out=None, extra_args=None):
    """用模板构建网页。返回 (ok, 消息)。from_json 仅为接口兼容保留。"""
    out = out or INDEX_HTML
    cmd = [sys.executable, os.path.join(BASE_DIR, "app", "build_map_html.py"), "--out", out]
    if extra_args:
        cmd.extend(extra_args)
    r = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "构建失败")[-800:]
    ok, msg = verify(out)
    return ok, (r.stdout or "").strip() + "\n" + msg


def verify(path):
    """产物安全检查：文件存在、单一数据源、没有旧数据源与凭证残留。"""
    if not os.path.exists(path):
        return False, "✗ 网页文件不存在：%s" % path
    if os.path.getsize(path) < 20000:
        return False, "✗ 网页文件过小（%d 字节），可能构建异常" % os.path.getsize(path)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    if "./data.json" not in text:
        return False, "✗ 网页没有指向 ./data.json"
    for pattern in FORBIDDEN_PATTERNS:
        if pattern.search(text):
            return False, "✗ 网页包含旧数据源或凭证残留：%s" % pattern.pattern
    return True, "✓ 网页自检通过（%.1f KB，唯一数据源 ./data.json）" % (os.path.getsize(path) / 1024)


def copy_to_dist(src_html=INDEX_HTML, src_json=None, dist_dir=None):
    """整理发布目录：只放 index.html 与脱敏 data.json。"""
    from ..core.paths import DATA_JSON, DIST_DIR
    from ..data.atomic import atomic_copy
    dist_dir = dist_dir or DIST_DIR
    os.makedirs(dist_dir, exist_ok=True)
    atomic_copy(src_html, os.path.join(dist_dir, "index.html"))
    if src_json:
        atomic_copy(src_json, os.path.join(dist_dir, "data.json"))
    return dist_dir
