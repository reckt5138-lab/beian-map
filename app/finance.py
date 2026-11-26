# -*- coding: utf-8 -*-
"""合同金额、回款与发货金额的精确计算（Decimal，不使用浮点数）。

设计原则：
- 所有金额以字符串或数字进入，统一转 Decimal 后计算，输出两位小数字符串；
- 数据缺失与“金额为 0”严格区分，绝不用 0 冒充未知；
- 异常不静默：金额为 0、回款超过合同、产品金额缺失、发货缺失都写入 anomalies，
  前端可据此提示，接口层也能据此拒绝错误数据。
- 作废/冲销/退款默认不计入有效回款，这是本模块的默认业务口径；若上游财务规则不同，
  必须由后端调整 VALID/EXCLUDED 规则，不能在前端改数。
"""

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0.00")

VOID_KEYWORDS = ("作废", "冲销", "退款", "红冲", "撤销", "无效", "void", "reverse", "refund", "cancel")

# 公开数据中绝对不允许出现的财务键名，用于发布前自检
FINANCE_KEYS = (
    "contractAmount", "receivedAmount", "unreceivedAmount", "collectionRate",
    "receipts", "products", "deliveries", "shippedAmount", "contractNo",
)


def parse_amount(value):
    """把 "¥10,000.00" / 10000 / "10000.5" 转成 Decimal；空值返回 (None, None)；
    无法解析返回 (None, "invalid")。"""
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, "invalid"
    if isinstance(value, Decimal):
        return value, None
    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value)), None
        except InvalidOperation:
            return None, "invalid"
    text = str(value).strip()
    if not text:
        return None, None
    text = text.replace("¥", "").replace("￥", "").replace(",", "").replace("，", "")
    text = text.replace("元", "").replace(" ", "")
    try:
        return Decimal(text), None
    except InvalidOperation:
        return None, "invalid"


def round_money(value):
    if value is None:
        return None
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def money_text(value):
    """两位小数、千分位；None 返回 None（前端显示“暂无数据”）。"""
    value = round_money(value)
    if value is None:
        return None
    return "{:,.2f}".format(value)


def rate_text(value):
    if value is None:
        return None
    return "{:.2f}".format(value.quantize(CENT, rounding=ROUND_HALF_UP))


def _is_void(record):
    status = str((record or {}).get("status") or "").strip().lower()
    return any(k.lower() in status for k in VOID_KEYWORDS)


def sum_receipts(receipts):
    """累计有效回款。

    返回 (total, included_count, excluded_count, anomalies)。
    - 状态含作废/冲销/退款等关键词的记录不计入；
    - 金额为负的记录视为冲销，不计入；
    - 金额缺失或非法的记录不计入，并记录 anomaly。
    """
    total = ZERO
    included = 0
    excluded = 0
    anomalies = []
    for i, item in enumerate(receipts or []):
        amount, err = parse_amount((item or {}).get("amount"))
        if _is_void(item) or (amount is not None and amount < 0):
            excluded += 1
            continue
        if amount is None:
            excluded += 1
            anomalies.append({"code": "receipt_amount_invalid", "index": i, "message": "第 %d 笔回款金额缺失或非法" % (i + 1)})
            continue
        total += amount
        included += 1
    return total, included, excluded, anomalies


def compute_products(products):
    """计算合同产品明细与合计。

    每个产品：合同金额（product.amount），发货金额（deliveries 累计或 shippedAmount）。
    """
    rows = []
    total_contract = ZERO
    total_shipped = ZERO
    contract_known = 0
    shipped_known = 0
    anomalies = []
    for i, item in enumerate(products or []):
        item = item or {}
        name = str(item.get("name") or "").strip()
        if not name:
            anomalies.append({"code": "product_name_missing", "index": i, "message": "第 %d 行产品名称为空" % (i + 1)})
            continue
        amount, err = parse_amount(item.get("amount"))
        if err == "invalid":
            anomalies.append({"code": "product_amount_invalid", "index": i, "message": "产品「%s」金额格式非法" % name})
        shipped = None
        deliveries = item.get("deliveries")
        if deliveries:
            shipped = ZERO
            for j, d in enumerate(deliveries):
                d_amount, d_err = parse_amount((d or {}).get("amount"))
                if _is_void(d) or (d_amount is not None and d_amount < 0):
                    continue
                if d_amount is None:
                    anomalies.append({"code": "delivery_amount_invalid", "index": i, "delivery": j,
                                      "message": "产品「%s」第 %d 次发货金额缺失或非法" % (name, j + 1)})
                    continue
                shipped += d_amount
        else:
            shipped, s_err = parse_amount(item.get("shippedAmount"))
            if s_err == "invalid":
                anomalies.append({"code": "shipped_amount_invalid", "index": i, "message": "产品「%s」发货金额格式非法" % name})
            if shipped is None:
                anomalies.append({"code": "delivery_missing", "index": i, "message": "产品「%s」没有发货记录" % name})

        if amount is None:
            anomalies.append({"code": "product_amount_missing", "index": i, "message": "产品「%s」合同金额缺失" % name})
        else:
            total_contract += amount
            contract_known += 1
        if shipped is not None:
            total_shipped += shipped
            shipped_known += 1

        rows.append({
            "seq": len(rows) + 1,
            "name": name,
            "contractAmount": money_text(amount),
            "shippedAmount": money_text(shipped),
        })

    incomplete = (contract_known < len(rows)) or (shipped_known < len(rows))
    if incomplete and rows:
        anomalies.append({"code": "totals_incomplete", "message": "部分产品金额缺失，合计仅统计有值的产品"})
    return {
        "products": rows,
        "totalContractAmount": money_text(total_contract) if contract_known else None,
        "totalShippedAmount": money_text(total_shipped) if shipped_known else None,
        "productsIncomplete": incomplete,
        "anomalies": anomalies,
    }


def compute_contract(contract):
    """计算单份合同的金额、未回金额、回款率及产品明细。"""
    contract = contract or {}
    contract_no = str(contract.get("contractNo") or "").strip()
    status = str(contract.get("contractStatus") or "").strip()
    pending = bool(contract.get("financialsPending"))
    anomalies = []

    amount, amount_err = parse_amount(contract.get("contractAmount"))
    if amount_err == "invalid":
        anomalies.append({"code": "contract_amount_invalid", "message": "合同金额格式非法"})
    if amount is None:
        anomalies.append({"code": "contract_amount_missing", "message": "合同金额缺失，无法计算回款率"})

    receipts = contract.get("receipts")
    received = None
    if pending:
        anomalies.append({"code": "financials_pending",
                          "message": "合同状态为「%s」，回款尚未生效，不计入项目回款" % (status or "未通过")})
    elif receipts:
        received, included, excluded, r_anoms = sum_receipts(receipts)
        anomalies.extend(r_anoms)
        if excluded:
            anomalies.append({"code": "receipts_excluded", "message": "%d 笔作废/冲销/退款记录未计入回款" % excluded})
    else:
        received, r_err = parse_amount(contract.get("receivedAmount"))
        if r_err == "invalid":
            anomalies.append({"code": "received_amount_invalid", "message": "已回款金额格式非法"})
        if received is None:
            received = ZERO
            anomalies.append({"code": "receipts_missing", "message": "没有回款记录，暂按 0 元统计"})

    unreceived = None
    rate = None
    if amount is None or received is None:
        unreceived = None
    else:
        unreceived = amount - received
        if unreceived < 0:
            anomalies.append({"code": "received_exceeds_contract",
                              "message": "回款金额超过合同金额，差额 %.2f 元，请核对财务数据" % abs(unreceived)})
        if amount == 0:
            anomalies.append({"code": "contract_amount_zero", "message": "合同金额为 0，回款率无法计算"})
            rate = None
        else:
            rate = received / amount * Decimal("100")

    product_result = compute_products(contract.get("products"))
    anomalies.extend(product_result["anomalies"])

    return {
        "contractNo": contract_no,
        "contractStatus": status,
        "isSubContract": bool(contract.get("isSubContract")),
        "financialsPending": pending,
        "contractAmount": money_text(amount),
        "receivedAmount": money_text(received),
        "unreceivedAmount": money_text(unreceived),
        "collectionRate": rate_text(rate),
        "products": product_result["products"],
        "totalContractAmount": product_result["totalContractAmount"],
        "totalShippedAmount": product_result["totalShippedAmount"],
        "productsIncomplete": product_result["productsIncomplete"],
        "anomalies": anomalies,
    }


def compute_contracts(contracts):
    """多份合同逐条计算，并返回项目层面的汇总（供详情页顶部使用）。"""
    computed = [compute_contract(c) for c in (contracts or [])]
    total_contract = ZERO
    total_received = ZERO
    total_unreceived = ZERO
    has_amount = False
    has_received = False
    for c in computed:
        amount = parse_amount(c["contractAmount"])[0]
        recv = parse_amount(c["receivedAmount"])[0]
        unre = parse_amount(c["unreceivedAmount"])[0]
        if amount is not None:
            total_contract += amount
            has_amount = True
        if recv is not None:
            total_received += recv
            has_received = True
        if unre is not None:
            total_unreceived += unre
    rate = None
    if has_amount and total_contract > 0:
        rate = total_received / total_contract * Decimal("100")
    return {
        "contracts": computed,
        "summary": {
            "contractAmount": money_text(total_contract) if has_amount else None,
            "receivedAmount": money_text(total_received) if has_received else None,
            "unreceivedAmount": money_text(total_unreceived) if has_amount else None,
            "collectionRate": rate_text(rate),
        },
    }


def assert_no_finance(payload):
    """发布前自检：公开 payload 中不得出现合同/财务字段。返回 (ok, problems)。

    说明：公开脱敏数据允许存在被清空的占位键（如 contractNo: ""），
    但绝不允许有值；合同金额、回款、产品、发货等键连键名都不应出现。
    """
    problems = []
    blank_keys = ("contractNo", "contractNoText", "contractStatus", "contractAmount",
                  "receivedAmount", "unreceivedAmount", "collectionRate",
                  "products", "deliveries", "shippedAmount")
    for i, proj in enumerate((payload or {}).get("projects") or []):
        for key in FINANCE_KEYS:
            if key not in proj:
                continue
            value = proj.get(key)
            if key in blank_keys:
                if value not in (None, "", [], {}):
                    problems.append("projects[%d].%s 有值，合同财务信息不得进入公开数据" % (i, key))
            else:
                problems.append("projects[%d].%s 键存在，公开数据不应包含财务字段" % (i, key))
        for name in (proj.get("fields") or {}):
            if re.search(r"合同编号|合同金额|回款|未回|发货", str(name)):
                problems.append("projects[%d].fields 含财务字段：%s" % (i, name))
    header = ((payload or {}).get("rows") or [[]])[0]
    for name in header:
        if re.search(r"合同金额|回款|未回|发货金额", str(name)):
            problems.append("rows 含财务列：%s" % name)
    return (not problems), problems
