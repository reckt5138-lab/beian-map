"""统一命令行入口：python -m app.main <命令>

命令：
    crawl        抓一次数据（不写飞书），产出 output/data.full.json + Excel
    build-json   用 output/data.full.json（或指定文件）生成脱敏 data.json
    build-map    用 data.json 构建 index.html
    publish      完整发布链：脱敏 → 校验 → 构建 → 自检 → 生成 dist/
    validate     只做数据校验（不写文件）
    diagnose     输出诊断报告到 output/logs/diagnostic_report.txt
    selftest     跑一遍离线自检（不需要账号）

旧入口（app/crawler.py、app/build_map_html.py）继续可用；离线转换请用 build-json 子命令。
"""

import argparse
import json
import os
import subprocess
import sys

# 允许 `python app\main.py ...` 直接运行（此前只支持 `python -m app.main`）
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "app"

from . import __version__
from .core import ensure_dirs, load_config, setup_logging
from .core.exceptions import JbufaError
from .core.paths import BASE_DIR, DATA_JSON, DIST_DIR, FULL_JSON, INDEX_HTML, MAP_HTML_LOCAL
from .data import export_public, load_previous, validate_payload
from .map import build_page, copy_to_dist
from .security import assert_safe, sanitize


def _run_crawler(json_out, extra=None):
    cmd = [sys.executable, os.path.join(BASE_DIR, "app", "crawler.py"),
           "--no-feishu", "--json-out", json_out]
    if extra:
        cmd.extend(extra)
    return subprocess.call(cmd, cwd=BASE_DIR)


def cmd_crawl(args):
    ensure_dirs()
    out = args.out or FULL_JSON
    code = _run_crawler(out)
    if code != 0:
        print("抓取失败，退出码 %s。日志：output/logs/" % code)
        return code
    if not os.path.exists(out):
        print("抓取结束但没找到 %s" % out)
        return 1
    with open(out, "r", encoding="utf-8") as f:
        payload = json.load(f)
    ok, report = validate_payload(payload, load_previous(os.path.join(os.path.dirname(out), "data.prev.json")))
    print("数据校验：%s（%d 条 / %s 列）" % ("通过" if ok else "未通过", report["count"], report["columns"]))
    for p in report["problems"]:
        print("  ✗", p)
    return 0 if ok else 4


def cmd_build_json(args):
    src = args.source or FULL_JSON
    if not os.path.exists(src):
        print("找不到源数据：%s\n先运行 python -m app.main crawl" % src)
        return 1
    with open(src, "r", encoding="utf-8") as f:
        full = json.load(f)
    previous = load_previous(DATA_JSON)
    public = export_public(full, args.out or DATA_JSON, previous=previous)
    ok, problems = assert_safe(public)
    if not ok:
        print("✗ 安全检查未通过：\n  - " + "\n  - ".join(problems))
        return 5
    print("✓ 已生成公开数据 %s（%d 条 / %d 列）" % (args.out or DATA_JSON, public["count"], public["columns"]))
    return 0


def cmd_build_map(args):
    ok, msg = build_page(from_json=args.source or "data.json", out=args.out)
    print(msg)
    return 0 if ok else 1


def cmd_publish(args):
    code = cmd_build_json(argparse.Namespace(source=args.source, out=args.out or DATA_JSON))
    if code != 0:
        return code
    with open(args.out or DATA_JSON, "r", encoding="utf-8") as f:
        public = json.load(f)
    ok, problems = assert_safe(public)
    if not ok:
        print("✗ 发布前自检失败：\n  - " + "\n  - ".join(problems))
        return 5

    ok, msg = build_page(from_json=args.out or "data.json", out=INDEX_HTML)
    print(msg)
    if not ok:
        print("✗ 网页构建失败，保留上一版，不发布")
        return 1
    build_page(from_json=args.out or "data.json", out=MAP_HTML_LOCAL)
    copy_to_dist(INDEX_HTML, args.out or DATA_JSON, DIST_DIR)
    print("✓ 发布目录已生成：%s（只含 index.html 与脱敏 data.json）" % DIST_DIR)
    return 0


def cmd_validate(args):
    with open(args.source or DATA_JSON, "r", encoding="utf-8") as f:
        payload = json.load(f)
    ok, report = validate_payload(payload, load_previous(DATA_JSON) if args.compare else None)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 4


def cmd_diagnose(args):
    import importlib.util
    path = os.path.join(BASE_DIR, "scripts", "maintenance.py")
    spec = importlib.util.spec_from_file_location("maintenance", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    print("诊断报告：" + mod.write_diagnostic_report())
    return 0


def cmd_selftest(args):
    """离线自检：用 data.json 反推脱敏 → 校验 → 构建临时页面，不需要账号。"""
    ensure_dirs()
    with open(DATA_JSON, "r", encoding="utf-8") as f:
        payload = json.load(f)
    public = sanitize(payload)
    ok, problems = assert_safe(public)
    print("脱敏自检：%s" % ("通过" if ok else "失败：" + "; ".join(problems)))
    ok2, report = validate_payload(public)
    print("校验：%s（%d 条）" % ("通过" if ok2 else "失败：" + "; ".join(report["problems"]), report["count"]))
    tmp = os.path.join(BASE_DIR, "output", "_selftest.html")
    ok3, msg = build_page(from_json=DATA_JSON, out=tmp)
    print("构建自检：" + (msg.splitlines()[-1] if msg else "无输出"))
    return 0 if (ok and ok2 and ok3) else 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m app.main", description="青鸾备案项目地图 V%s" % __version__)
    parser.add_argument("-v", "--verbose", action="store_true", help="输出更多日志")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("crawl", help="抓一次数据（产出完整 JSON + Excel）")
    p.add_argument("--out", default="", help="完整数据输出路径，默认 output/data.full.json")
    p.set_defaults(func=cmd_crawl)

    p = sub.add_parser("build-json", help="生成脱敏 data.json")
    p.add_argument("--source", default="", help="完整数据来源，默认 output/data.full.json")
    p.add_argument("--out", default="", help="输出路径，默认 data.json")
    p.set_defaults(func=cmd_build_json)

    p = sub.add_parser("build-map", help="构建 index.html")
    p.add_argument("--source", default="", help="数据来源，默认 data.json")
    p.add_argument("--out", default="", help="输出文件，默认 index.html")
    p.set_defaults(func=cmd_build_map)

    p = sub.add_parser("publish", help="完整发布链（脱敏→校验→构建→dist）")
    p.add_argument("--source", default="", help="完整数据来源")
    p.add_argument("--out", default="", help="公开数据输出")
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("validate", help="校验数据")
    p.add_argument("--source", default="", help="默认 data.json")
    p.add_argument("--compare", action="store_true", help="与上一版比较，检查异常下降")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("diagnose", help="生成诊断报告")
    p.set_defaults(func=cmd_diagnose)

    p = sub.add_parser("selftest", help="离线自检")
    p.set_defaults(func=cmd_selftest)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    setup_logging("app")
    try:
        return args.func(args)
    except JbufaError as exc:
        print("✗ " + exc.as_text())
        return exc.exit_code


if __name__ == "__main__":
    sys.exit(main())

