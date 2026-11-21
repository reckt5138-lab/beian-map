r"""生成 data.json（网页读的那份），不经过飞书。

正常链路（云端 / 本地测试都一样）：
    python app\crawler.py --no-feishu --json-out data.json
    爬虫抓完 → 直接写 data.json（列结构与 Excel 一致，走字段模板）

本脚本用于「已经有数据、只想重建 JSON」的场景：
    python app\build_data_json.py                  # 用 output\raw 里最新的一份原始 JSON
    python app\build_data_json.py --from-xlsx output\备案项目2026-11-21.xlsx
    python app\build_data_json.py --from-json data.json
    python app\build_data_json.py --dry-run

输出结构：

    {
      "generated_at": "2026-11-21T12:40:00+08:00",
      "updated": "2026-11-21 11:53:18",
      "source": "青鸾 https://c.jbufa.com（projects_2026-11-21.json）",
      "sheet": "备案项目",
      "columns": 158,
      "count": 18,
      "rows": [["项目名称", ...], ["..."]],
      "projects": [{"name": "...", "lat": 39.9, "lng": 116.4, ...}]
    }

幂等：内容没变就不重写文件（generated_at 也保留），云端不会产生无意义提交。
"""

import argparse
import glob
import json
import os
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR) if os.path.basename(SCRIPT_DIR).lower() == "app" else SCRIPT_DIR
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import map_payload as mp  # noqa: E402

OUT_PATH = os.path.join(BASE_DIR, "data.json")


# ------------------------------------------------------------------ 数据来源
def latest_raw():
    """output/raw 里最新的 projects_*.json。"""
    raw_dir = os.path.join(BASE_DIR, "output", "raw")
    files = sorted(glob.glob(os.path.join(raw_dir, "projects_*.json")))
    return files[-1] if files else ""


def matrix_from_raw(raw_path):
    """原始 JSON → 二维表。没有字段模板，列数可能比 Excel 多（会打印提示）。"""
    import crawler as cr  # 只有这条路径需要（它要读取导出参数）

    with open(raw_path, "r", encoding="utf-8-sig") as f:
        rows = json.load(f)
    if isinstance(rows, dict):
        rows = rows.get("rows") or rows.get("projects") or []
    if not rows:
        return [], 0
    cfg = cr.load_config()
    checkin = int((cfg.get("export") or {}).get("checkin_columns", 50))
    extra = (cfg.get("export") or {}).get("extra_fields") or []
    rows = cr.prepare_rows(rows, checkin)
    columns = cr.build_columns(rows, None, checkin, extra)
    print("提示：原始 JSON 模式没有字段模板，列数（%d）可能多于 Excel；正式流程请用 "
          "python app\\crawler.py --no-feishu --json-out data.json" % len(columns))
    return cr.build_matrix(columns, rows), len(columns)


def matrix_from_xlsx(path):
    """Excel（带表头） → 二维表。"""
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    matrix = []
    for row in ws.iter_rows(values_only=True):
        if not row:
            continue
        matrix.append(["" if v is None else v for v in row])
    while matrix and not any(str(v).strip() for v in matrix[-1]):
        matrix.pop()
    return matrix, len(matrix[0]) if matrix else 0


def build(raw_path=None, xlsx=None, from_json=None):
    if from_json:
        with open(from_json, "r", encoding="utf-8-sig") as f:
            snap = json.load(f)
        return {
            "updated": snap.get("updated") or "",
            "source": snap.get("source") or "本地快照 %s" % os.path.basename(from_json),
            "sheet": snap.get("sheet") or "备案项目",
            "columns": snap.get("columns") or (len((snap.get("rows") or [[]])[0])),
            "count": len(snap.get("projects") or []),
            "rows": snap.get("rows") or [],
            "projects": snap.get("projects") or [],
        }

    if xlsx:
        matrix, ncols = matrix_from_xlsx(xlsx)
        payload = mp.from_matrix(matrix, ncols,
                                 source="本地 Excel（%s）" % os.path.basename(xlsx),
                                 updated=datetime.fromtimestamp(os.path.getmtime(xlsx)).strftime("%Y-%m-%d %H:%M:%S"))
        return payload

    path = raw_path or latest_raw()
    if not path or not os.path.exists(path):
        raise SystemExit("找不到原始数据。先跑：python app\\crawler.py --no-feishu --json-out data.json")
    matrix, ncols = matrix_from_raw(path)
    return mp.from_matrix(matrix, ncols,
                          source="青鸾 %s（%s）" % ("https://c.jbufa.com", os.path.basename(path)),
                          updated=datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S"))


def main():
    ap = argparse.ArgumentParser(description="生成 data.json（不经过飞书）")
    ap.add_argument("--raw", default="", help="output/raw 下的 projects_*.json；默认取最新")
    ap.add_argument("--from-xlsx", default="", help="从 Excel 生成（列结构与 Excel 一致）")
    ap.add_argument("--from-json", default="", help="直接用已转好的 data.json / projects.json")
    ap.add_argument("--out", default=OUT_PATH, help="输出路径，默认项目根目录 data.json")
    ap.add_argument("--dry-run", action="store_true", help="只打印摘要，不写文件")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    payload = build(args.raw or None, args.from_xlsx or None, args.from_json or None)
    if args.dry_run:
        print("预览（未写盘）：%d 条 / %d 列 / 数据时间 %s"
              % (payload["count"], payload["columns"], payload["updated"]))
        return 0
    wrote, changed = mp.save(payload, args.out)
    tag = "无变化，跳过写入" if not changed else "已写出"
    print("%s：%s（%d 条 / %d 列 / 数据时间 %s）"
          % (tag, args.out, payload["count"], payload["columns"], payload["updated"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
