"""矩阵解析与坐标合并（原 sheet_to_projects 的核心部分，V3.0 改名）。

职责只有两件事：
- parse(matrix)：二维表（第一行表头）→ 项目字典列表 + 列数
- with_coords(projects)：给项目补经纬度（data/coords.json 精确值优先，区中心兜底）

被 app/map_payload.py 与 app/crawler.py 复用，不依赖任何外部接口。
"""

import json
import os

try:
    from . import project_type
except ImportError:  # 直接以 app/ 为工作目录运行时
    import project_type

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
    # 以下字段是项目分类与合同关联所需，来自青鸾导出列，不参与公开金额展示
    "项目编号": "projectCode",
    "项目状态": "status",
    "合同编号": "contractNo",
    "合同情况": "contractStatus",
    "成交时间": "dealTime",
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

DATE_FIELDS = ("filing", "expire", "created", "lastSign")
SIGN_PAIR_HEADERS = ("签到时间", "签到记录")


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


def _cell(v):
    if isinstance(v, list):
        # 富文本单元格：[{"type":"text","text":"..."}]
        return "".join(str(x.get("text", "")) if isinstance(x, dict) else str(x) for x in v)
    return "" if v is None else str(v)


def norm_date(s):
    """把 2026/12/11、2026-12-11 10:08:24 或 Excel 序列号统一成 YYYY-MM-DD。"""
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
    """二维表 → (项目列表, 列数)。第一行是表头。"""
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
        # 全部字段（只读展示用）：所有非空值都带上，重复表头加序号；
        # 签到时间/签到记录已转成 signs，这里跳过，避免重复上百列。
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
        project_type.annotate([p])
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
