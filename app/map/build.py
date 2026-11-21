"""地图构建：调用现有 build_map_html.py（保留 V2 模板与全部交互功能），
构建完成后做一次产物自检（文件非空、含 window.EMBEDDED、不含明文密钥）。
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
]


def build(from_json="data.json", out=None, extra_args=None):
    """用给定 JSON 构建网页。返回 (ok, 消息)。"""
    out = out or INDEX_HTML
    cmd = [sys.executable, os.path.join(BASE_DIR, "app", "build_map_html.py"),
           "--from-json", from_json, "--out", out]
    if extra_args:
        cmd.extend(extra_args)
    r = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "构建失败")[-800:]
    ok, msg = verify(out)
    return ok, (r.stdout or "").strip() + "\n" + msg


def verify(path):
    """产物安全检查：文件存在、有数据、没有凭证泄漏。"""
    if not os.path.exists(path):
        return False, "✗ 网页文件不存在：%s" % path
    if os.path.getsize(path) < 20000:
        return False, "✗ 网页文件过小（%d 字节），可能构建异常" % os.path.getsize(path)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    for pattern in FORBIDDEN_PATTERNS:
        if pattern.search(text):
            return False, "✗ 网页疑似包含凭证或明文密码，已阻止发布"
    if "window.EMBEDDED" not in text:
        return False, "✗ 网页缺少内置快照（window.EMBEDDED）"
    return True, "✓ 网页自检通过（%.1f KB）" % (os.path.getsize(path) / 1024)


def copy_to_dist(src_html=INDEX_HTML, src_json=None, dist_dir=None):
    """整理发布目录：只放脱敏后的 index.html 与 data.json。"""
    from ..core.paths import DATA_JSON, DIST_DIR
    from ..data.atomic import atomic_copy
    dist_dir = dist_dir or DIST_DIR
    os.makedirs(dist_dir, exist_ok=True)
    atomic_copy(src_html, os.path.join(dist_dir, "index.html"))
    if src_json:
        atomic_copy(src_json, os.path.join(dist_dir, "data.json"))
    return dist_dir
