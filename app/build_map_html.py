r"""把地图模板输出成 index.html。

V3.0 起页面只从同目录 ./data.json 取数，模板里不再注入任何数据、云端地址或内置快照，
所以这里只做一次模板 → 文件的拷贝。

    python app\build_map_html.py                        # 生成 index.html
    python app\build_map_html.py --out dist\index.html  # 指定输出
"""

import argparse
import os
import shutil
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

TEMPLATE_PATH = os.path.join(SCRIPT_DIR, "map_template.html")
INDEX_HTML = os.path.join(BASE_DIR, "index.html")


def build(src_path=TEMPLATE_PATH, out_path=None, payload=None, embed=True):
    """模板 → index.html。payload/embed 参数只为兼容旧调用保留，已不再使用。"""
    out_path = out_path or INDEX_HTML
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    shutil.copyfile(src_path, out_path)
    return out_path


def main():
    ap = argparse.ArgumentParser(description="生成地图页面 index.html")
    ap.add_argument("--src", default=TEMPLATE_PATH, help="模板 html，默认 app/map_template.html")
    ap.add_argument("--out", default=INDEX_HTML, help="输出路径，默认项目根目录 index.html")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    path = build(args.src, args.out)
    print("已写出：%s（%.1f KB）" % (path, os.path.getsize(path) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
