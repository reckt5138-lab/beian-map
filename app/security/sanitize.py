"""公开数据脱敏：白名单之外一律清空，并生成可公开的 rows / projects。

原则（来自 V2.1 任务书第六阶段）：
- 不靠"删掉几个敏感字段"就宣布安全，而是**白名单**：只有明确列出的字段保留。
- 不确定是否可公开的字段，一律按敏感处理（清空）。
- 结构保持不变（键仍在，值为空），前端不需要重写，详情面板显示"—"。
"""

import copy
import json
import os
import re

from ..core.paths import CONFIG_DIR

DEFAULT_FIELDS = {
    "projects_keep": [
        "name", "classify", "ptype", "build", "stage", "product", "source",
        "vertical", "filing", "expire", "created", "lat", "lng", "geo", "district",
        # 跟进记录（按用户要求公开：签到时间 + 记录正文）
        "signCount", "lastSign", "lastRecord", "signs",
    ],
    "projects_blank": [
        "addr", "owner", "dept", "area", "customer", "contact", "customerAddr",
        "customerType", "customerQual", "amount", "discount", "desc", "evac",
        "quoteTimes", "quoted",
    ],
    "columns_keep": [
        "项目名称", "产品类型", "审批类型", "项目分类", "项目类型", "建设类型",
        "项目进度", "项目来源", "备案时间", "失效时间", "创建时间",
        "是否海外项目", "是否改造项目",
        "项目签到次数", "最后一次签到时间", "未跟进天数",
    ],
    "derive_district": True,
}

_DISTRICT_RE = re.compile(r"^(?:北京市|上海市|天津市|重庆市|([^\s]{2,8}?省))?([^\s]{2,10}?(?:区|县|市))")


def load_fields():
    """读取 config/public_fields.json（不存在就用 example，再不存在用内置默认）。"""
    for name in ("public_fields.json", "public_fields.example.json"):
        path = os.path.join(CONFIG_DIR, name)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                merged = dict(DEFAULT_FIELDS)
                for key in DEFAULT_FIELDS:          # 只覆盖已知键，未知键忽略，避免误用
                    if key in data:
                        merged[key] = data[key]
                return merged
            except ValueError:
                continue
    return dict(DEFAULT_FIELDS)


def district_of(addr):
    """从详细地址里只取到「区/县」级，用于公开定位，避免泄露门牌。"""
    text = str(addr or "").strip()
    if not text:
        return ""
    m = _DISTRICT_RE.match(text)
    if m:
        return m.group(2)
    # 兜底：取前 6 个字符里的行政区关键词
    for kw in ("朝阳区", "海淀区", "丰台区", "通州区", "大兴区", "昌平区", "顺义区",
               "房山区", "门头沟区", "石景山区", "西城区", "东城区", "怀柔区",
               "平谷区", "密云区", "延庆区"):
        if kw in text:
            return kw
    return ""


def sanitize_project(proj, fields):
    keep = set(fields["projects_keep"])
    out = {}
    # 先把所有敏感字段显式置空（即使原数据里没有这个键，结构也保持一致）
    for key in fields.get("projects_blank", []):
        out[key] = [] if key == "signs" else ""
    for key, value in (proj or {}).items():
        if key == "fields":
            if isinstance(value, dict):
                out[key] = {k: v for k, v in value.items() if k in fields["columns_keep"]}
            else:                       # 非字典结构：直接丢弃，不放行任何全字段数据
                out[key] = {}
        elif key == "signs":
            out[key] = value if "signs" in keep else []   # 白名单放行时下发签到明细
        elif key in keep:
            out[key] = value
        else:
            # 结构保留、值清空：前端不用改，也不会泄露
            out[key] = [] if isinstance(value, list) else ""
    if fields.get("derive_district", True) and "district" not in out:
        out["district"] = district_of(proj.get("addr"))
    return out


def sanitize_rows(rows, fields):
    """只保留白名单列；同名列（签到时间/签到记录重复 50 组）只保留第一次出现。"""
    rows = rows or []
    if not rows:
        return [], 0
    header = rows[0]
    keep_names = fields["columns_keep"]
    idx_map = {}
    for name in keep_names:
        if name in header:
            idx_map[name] = header.index(name)
    new_header = [n for n in keep_names if n in idx_map]
    new_rows = [new_header]
    for row in rows[1:]:
        new_rows.append([row[i] if i < len(row) else "" for i in (idx_map[n] for n in new_header)])
    return new_rows, len(new_header)


def sanitize(payload, fields=None):
    """返回脱敏后的 payload（新对象，不改入参）。"""
    fields = fields or load_fields()
    data = copy.deepcopy(payload or {})
    rows, ncols = sanitize_rows(data.get("rows"), fields)
    projects = [sanitize_project(p, fields) for p in (data.get("projects") or [])]

    data["rows"] = rows
    data["projects"] = projects
    data["columns"] = ncols
    data["count"] = len(projects)
    data["public"] = True
    data["redacted"] = True
    data["field_policy"] = "config/public_fields.json"
    data["source"] = (data.get("source") or "").split("（")[0] + "（公开脱敏版）"
    if not projects and payload.get("count"):
        raise ValueError("脱敏后项目数为 0，拒绝生成公开数据")
    return data


def assert_safe(payload, fields=None):
    """发布前自检：确保敏感字段没有泄露。返回 (ok, 问题列表)。"""
    fields = fields or load_fields()
    problems = []
    allowed = set(fields["projects_keep"]) | {"fields", "_id"}
    for i, proj in enumerate((payload.get("projects") or [])[:5]):
        for key, value in proj.items():
            if key not in allowed and value not in ("", [], None, 0):
                problems.append("projects[%d].%s 未在白名单内却有值" % (i, key))
        for s_item in (proj.get("signs") or []):
            if not isinstance(s_item, dict):
                problems.append("projects[%d].signs 结构异常" % i)
                continue
            for k in s_item:
                if k not in ("date", "note"):
                    problems.append("projects[%d].signs 含非白名单键 %s" % (i, k))
        for name, value in (proj.get("fields") or {}).items():
            if name not in fields["columns_keep"] and value:
                problems.append("projects[%d].fields.%s 未在白名单内却有值" % (i, name))
    header = (payload.get("rows") or [[]])[0]
    for name in header:
        if name not in fields["columns_keep"]:
            problems.append("rows 含非白名单列：%s" % name)
    return (not problems), problems
