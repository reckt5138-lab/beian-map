r"""飞书在线表格 → 地图用的项目 JSON。

表格是「备案项目每日导出」（158 列，与网页导出一致）。本模块用自建应用身份
读取整张表，按表头名把 158 列还原成地图需要的字段，再补上坐标。

矩阵解析与坐标合并核心（`parse()` / `with_coords()`），被 map_payload 与 crawler 复用。
飞书取数部分为历史能力，当前主流程不调用（飞书链路已下线）；如需单独跑：
    python app\sheet_to_projects.py --out data\projects.json
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR) if os.path.basename(SCRIPT_DIR).lower() == "app" else SCRIPT_DIR
CONFIG_DIR = os.path.join(BASE_DIR, "config")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
SECRETS_PATH = os.path.join(CONFIG_DIR, "credentials.json")
DATA_DIR = os.path.join(BASE_DIR, "data")
COORDS_PATH = os.path.join(DATA_DIR, "coords.json")

# 表头名 → 输出字段。同名重复列（项目类型/项目进度）取第一列。
FIELD_MAP = {
    "项目名称": "name",
    "项目地址": "addr",
    "业务员": "owner",
    "部门": "dept",
    "面积": "area",
    "客户信息": "customer",
    "产品类型": "product",
    "项目分类": "classify",
    "项目类型": "ptype",
    "建设类型": "build",
    "项目进度": "stage",
    "预计合同金额": "amount",
    "折扣信息": "discount",
    "项目情况描述": "desc",
    "智能疏散跟进情况": "evac",
    "公司性质": "customerType",
    "公司资质": "customerQual",
    "职位": "contact",
    "公司地址": "customerAddr",
    "备案时间": "filing",
    "失效时间": "expire",
    "创建时间": "created",
    "最后一次签到时间": "lastSign",
    "项目签到次数": "signCount",
    "申请报价次数": "quoteTimes",
    "是否报价": "quoted",
    "项目来源": "source",
    "最后一次签到记录": "lastRecord",
    "项目工期": "duration",
    "垂直/非垂直": "vertical",
}

# 北京各区中心点，作为没有坐标的项目兜底（视觉上落在区内）
DISTRICT_CENTER = {
    "东城区": [39.928, 116.416],
    "西城区": [39.912, 116.366],
    "朝阳区": [39.948, 116.486],
    "海淀区": [39.959, 116.298],
    "丰台区": [39.858, 116.286],
    "石景山区": [39.906, 116.223],
    "通州区": [39.902, 116.658],
    "大兴区": [39.726, 116.338],
    "昌平区": [40.221, 116.231],
    "顺义区": [40.130, 116.654],
    "房山区": [39.749, 116.143],
    "门头沟区": [39.940, 116.102],
    "平谷区": [40.141, 117.121],
    "怀柔区": [40.316, 116.632],
    "密云区": [40.377, 116.843],
    "延庆区": [40.456, 115.975],
}


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


def load_conf(force=False):
    """返回飞书配置：config.feishu + credentials.json / 环境变量里的 app_secret。"""
    cfg = _read_json(CONFIG_PATH)
    conf = dict(cfg.get("feishu") or {})
    sec = _read_json(SECRETS_PATH)
    conf["app_id"] = os.environ.get("FEISHU_APP_ID") or conf.get("app_id") or sec.get("feishu_app_id") or ""
    conf["app_secret"] = (
        os.environ.get("FEISHU_APP_SECRET") or conf.get("app_secret") or sec.get("feishu_app_secret") or ""
    )
    conf.setdefault("api_base", "https://open.feishu.cn")
    return conf


def _http(method, url, body=None, token=None, timeout=20):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    if token:
        headers["Authorization"] = "Bearer %s" % token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


_TOKEN = {"token": "", "exp": 0}


def tenant_token(conf):
    if _TOKEN["token"] and _TOKEN["exp"] > time.time() + 60:
        return _TOKEN["token"]
    base = conf.get("api_base") or "https://open.feishu.cn"
    data = _http("POST", base + "/open-apis/auth/v3/tenant_access_token/internal",
                 {"app_id": conf["app_id"], "app_secret": conf["app_secret"]})
    if data.get("code") != 0:
        raise RuntimeError("飞书 tenant_access_token 失败：%s" % data)
    _TOKEN["token"] = data["tenant_access_token"]
    _TOKEN["exp"] = time.time() + int(data.get("expire") or 7200)
    return _TOKEN["token"]


def _token_of(conf):
    return (conf.get("spreadsheet_token") or "").strip()


def read_sheet(conf):
    """读出整张数据表（含表头），返回二维数组。"""
    token = _token_of(conf)
    sheet_id = conf.get("sheet_id") or ""
    base = conf.get("api_base") or "https://open.feishu.cn"
    meta = _http("GET", "%s/open-apis/sheets/v2/spreadsheets/%s/metainfo" % (base, token),
                 token=tenant_token(conf))
    if meta.get("code") != 0:
        raise RuntimeError("读取表格结构失败：%s" % meta)
    sheets = (meta.get("data") or {}).get("sheets") or []
    if not sheet_id:
        wanted = conf.get("sheet_name") or ""
        picked = next((s for s in sheets if s.get("title") == wanted), None) or (sheets[0] if sheets else None)
        if not picked:
            raise RuntimeError("表格里没有工作表")
        sheet_id = picked.get("sheetId") or picked.get("sheet_id")
    info = next((s for s in sheets if (s.get("sheetId") or s.get("sheet_id")) == sheet_id), {})
    rows = int(info.get("rowCount") or 200)
    cols = int(info.get("columnCount") or 200)

    def col_letter(n):
        out = ""
        while n:
            n, r = divmod(n - 1, 26)
            out = chr(65 + r) + out
        return out

    rng = "%s!A1:%s%d" % (sheet_id, col_letter(cols), rows)
    data = _http("GET", "%s/open-apis/sheets/v2/spreadsheets/%s/values/%s" % (base, token, urllib.parse.quote(rng)),
                 token=tenant_token(conf))
    if data.get("code") != 0:
        raise RuntimeError("读取表格内容失败：%s" % data)
    return ((data.get("data") or {}).get("valueRange") or {}).get("values") or []


def _cell(v):
    if isinstance(v, list):
        # 富文本单元格：[{"type":"text","text":"..."}]
        return "".join(str(x.get("text", "")) if isinstance(x, dict) else str(x) for x in v)
    return "" if v is None else str(v)


DATE_FIELDS = ("filing", "expire", "created", "lastSign")
SIGN_PAIR_HEADERS = ("签到时间", "签到记录")


def norm_date(s):
    """飞书表格的日期可能给 2026/12/11、2026-12-11 10:08:24 或 Excel 序列号，统一成 YYYY-MM-DD。"""
    s = "" if s is None else str(s).strip()
    if not s:
        return ""
    try:
        num = float(s)
        if 20000 < num < 80000:  # Excel 序列号（1899-12-30 起算）
            from datetime import date as _date, timedelta
            return (_date(1899, 12, 30) + timedelta(days=int(num))).strftime("%Y-%m-%d")
    except ValueError:
        pass
    head = s.split(" ")[0].split("T")[0].replace("/", "-").replace(".", "-")
    parts = head.split("-")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        y, m, d = (int(x) for x in parts)
        return "%04d-%02d-%02d" % (y, m, d)
    return s


def parse(matrix):
    if not matrix:
        return [], 0
    headers = [_cell(h).strip() for h in matrix[0]]
    pos = {}
    for i, h in enumerate(headers):
        if h and h not in pos:
            pos[h] = i
    sign_cols = [i for i, h in enumerate(headers) if h == "签到记录"]

    out = []
    for raw in matrix[1:]:
        if not any(_cell(x).strip() for x in raw):
            continue
        p = {}
        for label, key in FIELD_MAP.items():
            i = pos.get(label)
            p[key] = _cell(raw[i]).strip() if i is not None and i < len(raw) else ""
        signs = []
        for i in sign_cols:
            if i == 0 or i >= len(raw):
                continue
            note = _cell(raw[i]).strip()
            date = norm_date(_cell(raw[i - 1]))
            if note:
                signs.append({"date": date, "note": note})
        p["signs"] = signs
        # 全部字段（只读展示用）：158 列里所有非空值都带上，重复表头加序号；
        # 签到时间/签到记录已转成 signs，这里跳过，避免重复 100 列。
        seen = {}
        fields = []
        for i, h in enumerate(headers):
            if not h or h in SIGN_PAIR_HEADERS:
                continue
            if i >= len(raw):
                break
            v = _cell(raw[i]).strip()
            if not v:
                continue
            cnt = seen.get(h, 0) + 1
            seen[h] = cnt
            fields.append([h if cnt == 1 else "%s（%d）" % (h, cnt), v])
        p["fields"] = fields
        for k in DATE_FIELDS:
            p[k] = norm_date(p.get(k))
        if not p.get("name"):
            continue
        out.append(p)
    return out, len(headers)


def _jitter(name):
    """按项目名生成稳定的偏移，避免同区项目完全重叠。"""
    h = sum(ord(c) * (i + 7) for i, c in enumerate(str(name)))
    a = (h % 360) * 3.14159 / 180
    r = 0.012 + (h % 7) * 0.002
    return round(abs(h) % 1000 / 1000 * r * 0.4 + r * 0.0, 5), round(r * 0.5, 5)


def district_of(addr):
    s = str(addr or "")
    for d in DISTRICT_CENTER:
        if d in s:
            return d
    return ""


def with_coords(projects, coords=None):
    """补坐标：先用 coords.json 精确值，再按地址里的区中心兜底。"""
    coords = coords if coords is not None else _read_json(COORDS_PATH)
    out = []
    for p in projects:
        name = p.get("name", "")
        hit = coords.get(name)
        if hit and len(hit) == 2 and hit[0] and hit[1]:
            p["lat"], p["lng"] = float(hit[0]), float(hit[1])
            p["geo"] = "exact"
        else:
            d = district_of(p.get("addr"))
            if d:
                base = DISTRICT_CENTER[d]
                j1, j2 = _jitter(name)
                p["lat"] = round(base[0] + j1 - 0.004, 6)
                p["lng"] = round(base[1] + j2 - 0.006, 6)
                p["geo"] = "district"
            else:
                p["lat"] = None
                p["lng"] = None
                p["geo"] = "none"
        out.append(p)
    return out


def build_payload():
    conf = load_conf()
    matrix = read_sheet(conf)
    projects, ncols = parse(matrix)
    projects = with_coords(projects)
    return {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "飞书在线表格 %s" % (_token_of(conf) or "-"),
        "sheet": conf.get("name") or "备案项目每日导出",
        "columns": ncols,
        "count": len(projects),
        "projects": projects,
    }


def main():
    ap = argparse.ArgumentParser(description="飞书表格 → 地图 JSON")
    ap.add_argument("--out", default=os.path.join(BASE_DIR, "projects.json"), help="输出 JSON 路径（默认项目根目录，网页直接读）")
    ap.add_argument("--print", action="store_true", help="只打印摘要，不写文件")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    payload = build_payload()
    if args.print:
        print("读取成功：%d 条 %d 列，更新时间 %s" % (payload["count"], payload["columns"], payload["updated"]))
        return 0
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print("已写出：%s（%d 条）" % (args.out, payload["count"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
