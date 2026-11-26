# -*- coding: utf-8 -*-
"""项目 ↔ 合同 ↔ 财务数据的受控组装。

数据边界：
- 项目分类、项目名称来自公开抓取结果；
- 合同编号来自项目记录中的真实字段 contractNo（拆分多份合同，不做任何猜测）；
- 合同金额、回款、产品、发货只来自财务数据文件（由受控后端导出），本模块不生成任何演示值；
- 产物固定标记 restricted=True，并由 CLI 写到 private 目录，绝不进入 dist / Pages。
"""

import json
import re

from . import finance
from .project_type import ensure_kind

STATUS_OK = "ok"
STATUS_NO_CONTRACT = "no_contract"
STATUS_NO_RECORD = "no_finance_record"
STATUS_NO_SOURCE = "source_not_configured"

CONTRACT_SPLIT_RE = re.compile(r"[,，;；、\n\r]+")


def split_contract_nos(value):
    """把合同编号字段拆成多份；保留编号中的连字符与斜杠，只按明显分隔符拆分。"""
    text = str(value or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in CONTRACT_SPLIT_RE.split(text) if p.strip()]
    seen = []
    for p in parts:
        if p not in seen:
            seen.append(p)
    return seen


def extract_contract_nos(project):
    nos = split_contract_nos((project or {}).get("contractNo"))
    if not nos:
        nos = split_contract_nos((project or {}).get("contractNoText"))
    return nos


def load_finance_source(path):
    """读取财务导出文件。结构：{"updated": "...", "contracts": [...]}"""
    if not path:
        return None
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("contracts"), list):
        raise ValueError("财务数据格式错误：缺少 contracts 数组")
    return data


def _index_finance(finance_source):
    by_no = {}
    for item in (finance_source or {}).get("contracts") or []:
        no = str((item or {}).get("contractNo") or "").strip()
        if not no:
            continue
        by_no.setdefault(no, []).append(item)
    return by_no


def _match(records, project_name):
    if not records:
        return None
    for r in records:
        pname = str(r.get("projectName") or "").strip()
        if not pname or pname == project_name:
            return r
    return records[0]


def _match_records(index, contract_no, project_name):
    """按合同编号取记录：优先精确匹配，其次匹配“基础编号 + 字母后缀”的真实合同号。

    线上同一份合同可能登记为 26-01.BJ3580054ZA，而项目字段里是 26-01.BJ3580054Z；
    后缀视为同一合同的版本标记，但只在后缀为纯字母时成立，避免误配其他合同。
    """
    from .order_source import contract_no_matches

    records = list(index.get(contract_no) or [])
    for actual_no, items in index.items():
        if actual_no == contract_no:
            continue
        if contract_no_matches(contract_no, actual_no):
            records.extend(items)
    if not records:
        return []
    # 项目名能对上时优先保留同项目记录；同名多份则全部保留（多合同场景）
    same_project = [r for r in records
                    if str(r.get("projectName") or "").strip() == project_name]
    return same_project or records


def build_project_contracts(full_payload, finance_source=None):
    """返回 {projects: {项目名称: {status, contracts, summary}}}，金额全部为两位小数字符串。"""
    index = _index_finance(finance_source)
    projects_out = {}
    for proj in (full_payload or {}).get("projects") or []:
        name = str(proj.get("name") or "").strip()
        if not name:
            continue
        kind = ensure_kind(proj)
        nos = extract_contract_nos(proj)
        matched = []
        missing = []
        seen_record_nos = set()
        for no in nos:
            records = _match_records(index, no, name)
            if not records:
                missing.append(no)
                continue
            for record in records:
                record_no = str(record.get("contractNo") or "").strip()
                if record_no and record_no in seen_record_nos:
                    continue
                seen_record_nos.add(record_no)
                matched.append(record)
        # 成交项目：订单模块里同一项目名下可能还有项目字段未列出的真实合同，
        # 按“项目名完全一致”补挂，避免 12 个成交项目下漏掉真实订单
        if finance_source and kind == "deal":
            for record in (finance_source or {}).get("contracts") or []:
                if str(record.get("projectName") or "").strip() != name:
                    continue
                record_no = str(record.get("contractNo") or "").strip()
                if record_no and record_no in seen_record_nos:
                    continue
                seen_record_nos.add(record_no)
                matched.append(record)
                if record_no and record_no not in nos:
                    nos.append(record_no)

        # 财务数据里登记了合同、但项目记录没有编号：仍按真实财务记录关联（不丢数据）
        if not nos and finance_source:
            for no, records in index.items():
                record = _match(records, name)
                if record and str(record.get("projectName") or "").strip() == name:
                    matched.append(record)
                    nos.append(no)

        if not nos and not matched:
            projects_out[name] = {
                "status": STATUS_NO_CONTRACT,
                "pkind": kind,
                "contracts": [],
                "summary": None,
            }
            continue

        if finance_source is None:
            projects_out[name] = {
                "status": STATUS_NO_SOURCE,
                "pkind": kind,
                "contracts": [{
                    "contractNo": no,
                    "contractAmount": None,
                    "receivedAmount": None,
                    "unreceivedAmount": None,
                    "collectionRate": None,
                    "products": [],
                    "anomalies": [{"code": "finance_not_available",
                                   "message": "财务数据源未接入，无法展示金额与回款"}],
                } for no in nos],
                "summary": None,
            }
            continue

        if matched:
            result = finance.compute_contracts(matched)
            projects_out[name] = {
                "status": STATUS_OK,
                "pkind": kind,
                "contracts": result["contracts"],
                "summary": result["summary"],
                "missingContractNos": missing,
            }
        else:
            projects_out[name] = {
                "status": STATUS_NO_RECORD,
                "pkind": kind,
                "contracts": [{
                    "contractNo": no,
                    "contractAmount": None,
                    "receivedAmount": None,
                    "unreceivedAmount": None,
                    "collectionRate": None,
                    "products": [],
                    "anomalies": [{"code": "finance_record_missing",
                                   "message": "合同编号存在，但财务数据中没有对应记录"}],
                } for no in nos],
                "summary": None,
            }

    return {
        "updated": (finance_source or {}).get("updated") or "",
        "source": "受控财务数据（非公开）",
        "restricted": True,
        "note": "本文件含合同与财务信息，禁止放入 dist、Pages 或公开仓库。",
        "projects": projects_out,
    }


def save(payload, out_path):
    from .data.atomic import atomic_write_json
    atomic_write_json(out_path, payload)
    return out_path
