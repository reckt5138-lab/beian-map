r"""把二维表转成地图/网页用的 data.json 结构（爬虫与 app.main 共用）。

只依赖 sheet_to_projects，不 import crawler，避免循环引用。
"""

import json
import os

import sheet_to_projects as stp


def from_matrix(matrix, ncols=None, source="", sheet="备案项目", updated=""):
    """matrix（第一行表头，与 Excel 同序）→ data.json 的 payload。"""
    projects, n = stp.parse(matrix)
    if not projects:
        raise RuntimeError("二维表里没有可用项目（检查表头是否有「项目名称」）")
    projects = stp.with_coords(projects)
    return {
        "updated": updated,
        "source": source,
        "sheet": sheet,
        "columns": ncols or n,
        "count": len(projects),
        "rows": matrix,
        "projects": projects,
    }


def core(data):
    return {k: v for k, v in data.items() if k != "generated_at"}


def save(payload, out_path):
    """幂等 + 原子写入：内容没变就不动文件；变了先写临时文件再替换。

    V2.1：普通 open(...,'w') 会在写入中途被打断时留下半截 JSON，
    导致网页读到坏文件。改为原子替换（app/data/atomic.py）。
    """
    from datetime import datetime, timezone

    old = None
    if os.path.exists(out_path):
        try:
            with open(out_path, "r", encoding="utf-8-sig") as f:
                old = json.load(f)
        except Exception:
            old = None
    if old and core(old) == core(payload):
        return False, False
    payload["generated_at"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    try:  # 优先走统一原子写；老脚本单独跑时也不能崩
        import sys
        _here = os.path.dirname(os.path.abspath(__file__))
        if _here not in sys.path:
            sys.path.insert(0, _here)
        from data.atomic import atomic_write_json
        atomic_write_json(out_path, payload)
    except Exception:
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
            f.write("\n")
    return True, True
