"""原子写入：先写临时文件，再 os.replace 覆盖。

为什么必须：程序或机器在中途中断时，不能留下半截 data.json / Excel，
否则网页读到坏 JSON 会白屏，且上一版可用数据被破坏。
"""

import json
import os
import shutil
import tempfile


def atomic_write_bytes(path, data):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=d)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def atomic_write_text(path, text, encoding="utf-8"):
    atomic_write_bytes(path, text.encode(encoding))


def atomic_write_json(path, payload, indent=1):
    text = json.dumps(payload, ensure_ascii=False, indent=indent) + "\n"
    atomic_write_text(path, text)


def atomic_copy(src, dst):
    d = os.path.dirname(os.path.abspath(dst))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=d)
    os.close(fd)
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def backup_file(path, backup_dir):
    """把现有文件复制到备份目录（带时间戳），文件不存在就跳过。"""
    if not os.path.exists(path):
        return None
    from datetime import datetime
    os.makedirs(backup_dir, exist_ok=True)
    name = "%s.%s.bak" % (os.path.basename(path), datetime.now().strftime("%Y%m%d_%H%M%S"))
    dst = os.path.join(backup_dir, name)
    atomic_copy(path, dst)
    return dst
