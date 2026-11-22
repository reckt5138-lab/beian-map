"""JSON 导出：把「表头 + 数据行」矩阵转成网页 payload，并做原子写入。

与 app/map_payload.py 的关系：map_payload 是 V2 的实现（crawler 直接依赖），
本模块在它之上补了「原子写 + 校验 + 脱敏开关」，新代码优先用这里。
"""

import json
import os

from ..security.sanitize import sanitize
from .atomic import atomic_write_json, backup_file
from .validate import validate_payload

try:  # 复用 V2 的解析逻辑，避免两套字段映射造成不一致
    from .. import map_payload as _legacy_payload
except Exception:  # pragma: no cover
    _legacy_payload = None


def matrix_to_payload(matrix, ncols=None, source="", sheet="备案项目", updated=""):
    if _legacy_payload is None:
        raise RuntimeError("缺少 app/map_payload.py，无法解析矩阵")
    return _legacy_payload.from_matrix(matrix, ncols, source=source, sheet=sheet, updated=updated)


def core(data):
    """比较用：去掉 generated_at，避免"只是时间变了"被当成数据变化。"""
    return {k: v for k, v in (data or {}).items() if k != "generated_at"}


def same_data(a, b):
    return core(a) == core(b)


def save_payload(payload, path, atomic=True, make_backup=True, backup_dir=None):
    """幂等写入：业务内容没变就不落盘。返回 (写入?, 变化?)。"""
    old = None
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                old = json.load(f)
        except Exception:
            old = None
    if old is not None and same_data(old, payload):
        return False, False

    if make_backup and backup_dir:
        backup_file(path, backup_dir)

    from datetime import datetime, timezone
    payload = dict(payload)
    payload["generated_at"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    if atomic:
        atomic_write_json(path, payload)
    else:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
            f.write("\n")
    return True, True


def export_public(full_payload, out_path, fields=None, previous=None, backup_dir=None):
    """完整数据 → 脱敏数据 → 校验 → 原子写入。不通过就抛异常，上一版文件保持原样。"""
    public = sanitize(full_payload, fields)
    if previous is not None:
        validate_payload(public, previous, require_rows=True)
    save_payload(public, out_path, backup_dir=backup_dir)
    return public
