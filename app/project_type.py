# -*- coding: utf-8 -*-
"""项目分类识别：备案 / 成交 / 未知。

只依据业务字段判定，绝不根据项目名称、金额或合同是否存在猜测类型。
判定字段优先级：
    1. 项目分类（classify，来自“项目分类”列或 projectClassify/projectTabTypeName）
    2. 项目状态（status，来自 projectStatus）
值必须与业务字典完全一致（去掉首尾空白后比较）；不在字典内一律 unknown。
"""

FILING = "filing"
DEAL = "deal"
UNKNOWN = "unknown"

# 与青鸾系统中的真实取值保持一致。新增分类时必须同步这里和 docs。
# 注意：接口 `projectStatus` 的成交类取值是「成交」，网页 Tab 文案才是「成交项目」，
# 两者都必须识别，否则 12 条成交项目会被误判为 unknown。
FILING_VALUES = ("备案项目",)
DEAL_VALUES = ("成交项目", "成交")

KIND_LABELS = {FILING: "备案项目", DEAL: "成交项目", UNKNOWN: "未知类型"}


def _norm(value):
    return str(value or "").replace("\u3000", " ").strip()


def classify(project, filing_values=FILING_VALUES, deal_values=DEAL_VALUES):
    """返回 filing / deal / unknown。只看类型字段，不看名称与金额。"""
    project = project or {}
    for key in ("classify", "status", "projectStatus"):
        value = _norm(project.get(key))
        if not value:
            continue
        if value in filing_values:
            return FILING
        if value in deal_values:
            return DEAL
    return UNKNOWN


def annotate(projects, filing_values=FILING_VALUES, deal_values=DEAL_VALUES):
    """给每个项目写入 pkind 与 pkindLabel（原地修改并返回列表）。"""
    for p in projects or []:
        kind = classify(p, filing_values, deal_values)
        p["pkind"] = kind
        p["pkindLabel"] = KIND_LABELS[kind]
    return projects


def ensure_kind(project):
    """读 pkind；缺失或非法时按字段重新判定（用于兼容旧数据与脱敏输入）。"""
    kind = _norm(project.get("pkind")).lower() if project else ""
    if kind in (FILING, DEAL, UNKNOWN):
        return kind
    return classify(project)


def counts(projects):
    result = {FILING: 0, DEAL: 0, UNKNOWN: 0}
    for p in projects or []:
        result[ensure_kind(p)] += 1
    return result
