"""数据质量校验：发布前的最后一道闸门。

检查项（对应任务书 5.2）：
- 项目总数 / 是否 0 条
- 分页是否完成（payload 里 crawl_pages 有值时比对）
- 项目名是否重复（同一天同名项目只能出现一次）
- 必需字段（name）是否缺失
- 日期格式、经纬度是否合法
- 与上一版相比是否出现异常下降（阈值默认 60%）
"""

import json
import os
import re

from ..core.exceptions import DataValidationError

DATE_RE = re.compile(r"^(20\d{2}|19\d{2})-(\d{2})-(\d{2})")
REQUIRED_PROJECT_KEYS = ("name",)


def _load(path):
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None


def _valid_date(text):
    if not text:
        return True
    t = str(text).strip()
    if not t:
        return True
    return bool(DATE_RE.match(t))


def _valid_coord(lat, lng):
    if lat in (None, "", 0, "0") and lng in (None, "", 0, "0"):
        return True
    try:
        la, ln = float(lat), float(lng)
    except (TypeError, ValueError):
        return False
    return -90 <= la <= 90 and -180 <= ln <= 180


def validate(payload, previous=None, min_ratio=0.6, require_rows=True, allow_empty=False):
    """返回 (ok, 报告字典)。不通过时抛异常由调用方决定，这里先给结构化结果。"""
    problems = []
    warnings = []
    payload = payload or {}
    projects = payload.get("projects") or []
    count = len(projects)
    declared = payload.get("count")
    rows = payload.get("rows") or []

    if declared not in (None, "") and int(declared) != count:
        problems.append("count(%s) 与实际项目数(%d) 不一致" % (declared, count))
    if count == 0 and not allow_empty:
        problems.append("抓到 0 条项目，拒绝发布")
    if require_rows and (not rows or len(rows) < 2):
        problems.append("rows 为空（表头或数据行缺失）")

    pages_expected = payload.get("crawl_pages")
    pages_done = payload.get("crawl_pages_done")
    if pages_expected and pages_done is not None and int(pages_done) < int(pages_expected):
        problems.append("分页未完成：抓到 %s / %s 页" % (pages_done, pages_expected))

    seen = {}
    for i, proj in enumerate(projects):
        name = str(proj.get("name") or "").strip()
        if not name:
            problems.append("第 %d 条项目缺项目名称" % (i + 1))
            continue
        if name in seen:
            problems.append("项目名称重复：%s" % name[:40])
        seen[name] = i
        for key in ("filing", "expire", "created"):
            if not _valid_date(proj.get(key)):
                problems.append("%s 的 %s 不是合法日期：%r" % (name[:20], key, proj.get(key)))
                break
        if not _valid_coord(proj.get("lat"), proj.get("lng")):
            warnings.append("%s 坐标非法：%r / %r" % (name[:20], proj.get("lat"), proj.get("lng")))

    prev_count = None
    if isinstance(previous, dict):
        prev_count = previous.get("count")
    elif isinstance(previous, int):
        prev_count = previous
    if prev_count and count and count < prev_count * min_ratio:
        problems.append("数据异常下降：上次 %s 条，本次 %d 条（阈值 %d%%）"
                        % (prev_count, count, int(min_ratio * 100)))

    ok = not problems
    report = {
        "ok": ok,
        "count": count,
        "columns": payload.get("columns"),
        "previous_count": prev_count,
        "problems": problems,
        "warnings": warnings,
    }
    return ok, report


def validate_or_raise(payload, previous=None, min_ratio=0.6, require_rows=True, allow_empty=False):
    ok, report = validate(payload, previous, min_ratio, require_rows, allow_empty)
    if not ok:
        raise DataValidationError(
            "数据校验未通过，已保留上一版数据：\n  - " + "\n  - ".join(report["problems"]),
            hint="常见原因：青鸾登录失效、接口改版、账号无权限。日志见 output/logs/",
        )
    return report


def load_previous(path):
    return _load(path)


# 别名：供 app.data.__init__ / export_json 使用，避免与子模块名冲突
validate_payload = validate
