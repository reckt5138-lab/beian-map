r"""把数据写进地图 HTML（模板 + 内置快照 + 云端地址）。

没有服务器也能用：手机打开这个 html 文件就有数据；联网时页面会先试
GitHub 上的 data.json（Raw / jsDelivr），拿最新的一份，失败再退回内置快照。

    python app\build_map_html.py                                   # 刷新 备案项目地图.html 的内置快照
    python app\build_map_html.py --out index.html                  # 另存一份（给本地/Pages 用）
    python app\build_map_html.py --from-json projects.json --out index.html   # 不连飞书
    python app\build_map_html.py --no-embed --out index.html       # 不内置数据（体积小，纯云端）

云端仓库地址取自 config\config.json 的 publish 段（github_owner / github_repo / branch），
也可以用环境变量 GITHUB_REPOSITORY（Actions 自带，形如 owner/repo）覆盖。
"""

import argparse
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(BASE_DIR, "config")

HTML_PATH = os.path.join(BASE_DIR, "备案项目地图.html")
TEMPLATE_PATH = os.path.join(SCRIPT_DIR, "map_template.html")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
START = "/*__EMBEDDED_START__*/"
END = "/*__EMBEDDED_END__*/"
CLOUD_START = "/*__CLOUD_START__*/"
CLOUD_END = "/*__CLOUD_END__*/"


def rb(path):
    with open(path, "rb") as f:
        raw = f.read()
    return raw.decode("utf-8-sig", errors="replace")


def read_data_key():
    """解密密钥：config\\data_key.txt 优先，其次 config.json 的 publish.data_key。"""
    try:
        with open(os.path.join(CONFIG_DIR, "data_key.txt"), "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        pass
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            return ((json.load(f).get("publish") or {}).get("data_key") or "").strip()
    except Exception:
        return ""


def load_publish(data_file=""):
    """云端仓库地址 + 数据文件名 + 解密密钥（页面靠这三样读密文）。"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            conf = json.load(f)
    except Exception:
        conf = {}
    pub = conf.get("publish") or {}
    owner = str(pub.get("github_owner") or "").strip()
    repo = str(pub.get("github_repo") or "").strip()
    branch = str(pub.get("branch") or "main").strip() or "main"
    full = os.environ.get("GITHUB_REPOSITORY") or ""
    if full and "/" in full:
        owner, repo = full.split("/", 1)
    if not data_file:
        data_file = "data.enc" if os.path.exists(os.path.join(BASE_DIR, "data.enc")) else "data.json"
    key = read_data_key()
    if not owner or not repo:
        # 没配仓库地址也要带上密钥和文件名：本地 HTTP 打不开时至少能解密同目录密文
        return {"owner": "", "repo": "", "branch": branch, "file": data_file, "key": key} if key else None
    return {"owner": owner, "repo": repo, "branch": branch, "file": data_file, "key": key}


def replace_block(html, start, end, block, what):
    if start not in html or end not in html:
        raise RuntimeError("模板里找不到 %s 的标记：%s" % (what, start))
    i = html.index(start)
    j = html.index(end) + len(end)
    return html[:i] + block + html[j:]


def build(src_path=TEMPLATE_PATH, out_path=None, payload=None, embed=True):
    """模板（无数据）→ 取数 → 输出 html。payload 传入时用它代替飞书表。"""
    out_path = out_path or HTML_PATH
    if payload is None:
        try:
            import sheet_to_projects as _src          # 仅历史飞书取数路径需要
        except ImportError:
            raise RuntimeError("未传 payload，且飞书取数模块已移除：请用 --from-json 指定数据文件")
        payload = _src.build_payload()
    html = rb(src_path)

    if embed:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        data = data.replace("</", "<\\/")  # 避免提前结束 <script>
        block = (
            START
            + "\n/* 内置快照：由 app\\build_map_html.py 把最近一次的数据直接写进本文件，"
            + "没联网 / 打不开云端时也能看到内容。运行 build 脚本即可刷新。 */\n"
            + "window.EMBEDDED = "
            + data
            + ";\n"
            + END
        )
    else:
        block = START + "\nwindow.EMBEDDED = null;\n" + END
    html = replace_block(html, START, END, block, "内置快照")

    pub = load_publish()
    cloud_block = (
        CLOUD_START
        + "\n/* 云端地址：来自 config\\config.json 的 publish 段（或 GITHUB_REPOSITORY 环境变量）。"
        + "页面优先读 GitHub 上的 data.json，拿不到再用内置快照。 */\n"
        + ("window.CLOUD = %s;\n" % json.dumps(pub, ensure_ascii=False, separators=(",", ":"))
           if pub else "window.CLOUD = null;\n")
        + CLOUD_END
    )
    html = replace_block(html, CLOUD_START, CLOUD_END, cloud_block, "云端地址")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(html.encode("utf-8"))
    return out_path, payload


def payload_from_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description="把数据写进地图 HTML")
    ap.add_argument("--src", default=TEMPLATE_PATH, help="模板 html（不含数据），默认 app/map_template.html")
    ap.add_argument("--out", default=HTML_PATH, help="输出路径，默认项目根目录 备案项目地图.html")
    ap.add_argument("--from-json", default=None, help="不连飞书，用本地 JSON 快照（projects.json / data.json）")
    ap.add_argument("--no-embed", action="store_true", help="不内置数据快照，只留云端/同目录读取（文件更小）")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    payload = payload_from_json(args.from_json) if args.from_json else None
    path, payload = build(args.src, args.out or None, payload=payload, embed=not args.no_embed)
    print("已写出：%s（%d 条，数据时间 %s%s）"
          % (path, payload.get("count", 0), payload.get("updated", ""),
             "，无内置快照" if args.no_embed else "，含内置快照"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
