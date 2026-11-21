r"""直接抓青鸾 → data.json（不写飞书在线表格、不生成 Excel）。

新流水线的第一步：登录 → 抓列表 + 详情 → 拼成「表头 + 数据行」矩阵 → 落 data.json。
飞书表完全不参与，所以云端定时只需要青鸾账号，不需要飞书密钥。

    python app\crawl_to_data.py                      # 抓数 → 根目录 data.json
    python app\crawl_to_data.py --out output\data.json
    python app\crawl_to_data.py --no-detail          # 只抓列表字段，快但字段少
"""

import argparse
import json
import os
import sys
from datetime import date, datetime

import crawler as cw
import sheet_to_projects as src


def build(no_detail=False):
    cfg = cw.load_config()
    out_dir = cw.resolve_output_dir(cfg)
    cw.setup_logging(out_dir)

    client = cw.JBufaClient(cfg)
    client.login()

    template = None
    if cfg["export"].get("use_field_template", True):
        try:
            template = cw.load_field_template(client, cfg)
        except Exception as exc:      # 字段模板只是锦上添花
            cw.logging.warning("读取导出字段配置失败：%s", exc)

    rows, stats = cw.crawl_list(client, cfg)
    if not rows:
        raise SystemExit("没有抓到任何项目，检查账号权限或筛选条件")
    if no_detail:
        cfg["crawl"]["with_detail"] = False
        cfg["crawl"]["with_follow"] = False
    rows = cw.enrich_with_detail(client, cfg, rows)

    checkin = int(cfg["export"].get("checkin_columns", 50))
    cw.save_raw(out_dir, date.today().strftime("%Y-%m-%d"), rows)

    prepared = cw.prepare_rows(rows, checkin)
    columns = cw.build_columns(prepared, template, checkin, cfg["export"].get("extra_fields") or [])
    matrix = cw.build_matrix(columns, prepared)

    projects, ncols = src.parse(matrix)
    projects = src.with_coords(projects)
    return {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "青鸾接口直抓（不写飞书表）",
        "sheet": cfg["export"].get("file_prefix") or "备案项目",
        "columns": ncols,
        "table_columns": len(matrix[0]) if matrix else 0,
        "count": len(projects),
        "rows": matrix,
        "projects": projects,
    }


def main():
    ap = argparse.ArgumentParser(description="青鸾直抓 → data.json")
    ap.add_argument("--out", default=os.path.join(src.BASE_DIR, "data.json"))
    ap.add_argument("--no-detail", action="store_true", help="只抓列表字段，速度快")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    data = build(args.no_detail)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    print("已写出：%s（%d 条 / 表头 %d 列 / 数据时间 %s）"
          % (args.out, data["count"], data["table_columns"], data["updated"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
