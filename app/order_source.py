# -*- coding: utf-8 -*-
"""订单（合同）模块的真实数据抓取：合同金额、回款、产品、发货金额。

数据来源（青鸾线上接口，只读）：
- POST /contract/conditionsPage/v2   合同（订单）列表
- GET  /contract/{contractId}/overview 合同回款概况（合同金额/已回/未回/回款率/押金）
- GET  /contract/{contractId}          合同详情（quotationId 等）
- GET  /quotation/{quotationId}?merge=1&contractId=... 产品清单（含 cargoQuantity 发货数量）

所有金额保留原始接口值，不做估算；接口缺失字段一律留空并写入 anomalies。
"""

import datetime
import json

# 合同编号后缀：线上同一份合同可能登记为 26-01.BJ3580054ZA（末尾字母为版本/补充标记）
MAX_SUFFIX_LEN = 12


def contract_no_matches(base, actual):
    """合同编号匹配：完全一致，或实际编号 = 基础编号 + 纯字母后缀。"""
    base = str(base or "").strip()
    actual = str(actual or "").strip()
    if not base or not actual:
        return False
    if base == actual:
        return True
    if actual.startswith(base):
        suffix = actual[len(base):].rstrip(".")
        return bool(suffix) and len(suffix) <= MAX_SUFFIX_LEN and suffix.isalpha()
    return False


def _flatten_products(quotation):
    rows = []
    for system in (quotation or {}).get("systems") or []:
        template = (system or {}).get("template") or {}
        for table in template.get("templateTableList") or []:
            for item in (table or {}).get("quotationTableTupleList") or []:
                subs = (item or {}).get("subTuples") or []
                if subs:
                    rows.extend(subs)
                else:
                    rows.append(item)
    return rows


def _num(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def products_from_quotation(quotation, detail):
    """把报价产品转成 finance 需要的结构：合同金额=小计，发货金额=发货数量×合同单价。"""
    anomalies = []
    products = []
    for item in _flatten_products(quotation):
        name = str((item or {}).get("name") or "").strip()
        if not name:
            continue
        subtotal = _num(item.get("subtotal"))
        if subtotal is None:
            qty = _num(item.get("quantity"))
            price = _num(item.get("contractPrice"))
            if qty is not None and price is not None:
                subtotal = qty * price
        cargo_qty = _num(item.get("cargoQuantity"))
        price = _num(item.get("contractPrice"))
        if cargo_qty is None or price is None:
            shipped = None
            anomalies.append({"code": "delivery_quantity_missing",
                              "message": "产品「%s」缺少发货数量" % name})
        else:
            shipped = cargo_qty * price
        row = {"name": name, "amount": subtotal, "shippedAmount": shipped,
               "quantity": _num(item.get("quantity")), "cargoQuantity": cargo_qty}
        if subtotal is None:
            anomalies.append({"code": "product_amount_missing",
                              "message": "产品「%s」合同金额缺失" % name})
        products.append(row)
    if not products:
        anomalies.append({"code": "products_empty", "message": "报价单没有产品明细"})
    return products, anomalies


def fetch_contract_list(client, page_size=200):
    rows = []
    page_no = 1
    while True:
        res = client.call("POST", "/contract/conditionsPage/v2",
                          json_body={"pageNo": page_no, "pageSize": page_size})
        data = res.get("data") or []
        if not data:
            break
        rows.extend(data)
        total = res.get("total")
        try:
            total = int(total)
        except (TypeError, ValueError):
            total = None
        if total is None or len(rows) >= total or len(data) < page_size:
            break
        page_no += 1
    return rows


def fetch_contract_bundle(client, contract_id):
    detail = client.call("GET", "/contract/%s" % contract_id).get("data") or {}
    overview_rows = client.call("GET", "/contract/%s/overview" % contract_id).get("data") or []
    overview = overview_rows[0] if overview_rows else {}
    quotation = {}
    quotation_id = detail.get("quotationId")
    if quotation_id:
        quotation = client.call("GET", "/quotation/%s?merge=1&contractId=%s" % (quotation_id, contract_id)).get("data") or {}
    return detail, overview, quotation


def load_project_ids(raw_path):
    """从原始抓取行（output/raw/*.json）建立 项目名称 → 项目ID 映射。

    完整数据 data.full.json 为公开视图，不含内部项目ID；原始行才有 projectId。
    """
    with open(raw_path, "r", encoding="utf-8-sig") as f:
        rows = json.load(f)
    mapping = {}
    for row in rows or []:
        name = str((row or {}).get("projectName") or "").strip()
        pid = (row or {}).get("projectId") or (row or {}).get("id")
        if name and pid:
            mapping[name] = str(pid)
    return mapping


def fetch_project_contracts(client, project_id):
    """项目详情里的「合同情况」是权威合同清单，包含已驳回、OA审批中的全部合同。"""
    data = client.call("GET", "/project/%s" % project_id).get("data") or {}
    # 线上返回两种结构：扁平项目对象，或 {project, projectContact, ...}
    project = data.get("project") if isinstance(data, dict) and isinstance(data.get("project"), dict) else data
    return project.get("contractList") or []


def _build_record(client, project_name, base, bundle_cache, seen_cids):
    cid = str(base.get("contractId") or base.get("id") or "").strip()
    if not cid:
        return None
    duplicate = cid in seen_cids
    seen_cids.add(cid)
    try:
        if cid not in bundle_cache:
            bundle_cache[cid] = fetch_contract_bundle(client, cid)
        detail, overview, quotation = bundle_cache[cid]
        error = ""
    except Exception as exc:  # 单份合同失败不中断整体抓取
        detail, overview, quotation = {}, {}, {}
        error = str(exc)[:200]
    products, product_anomalies = products_from_quotation(quotation, detail)
    # 项目「合同情况」里同一 contractId 可能出现多行（主合同 + 补充协议/修订号），
    # 每行有独立合同金额；回款概况属于该订单，按订单口径展示，并在前端标注“并入主合同”。
    amount = base.get("contractAmount")
    if amount in (None, ""):
        amount = overview.get("contractAmount")
    received = overview.get("returnedAmount")
    if received is None:
        received = base.get("receivedAmount")
    if duplicate and received not in (None, "", 0, "0", "0.0", "0.00"):
        # 主合同已有回款时，不把整笔回款重复分摊到每个修订号
        received = None
    debt = overview.get("debtAmount")
    rate = overview.get("returnedPercentage")
    if duplicate:
        product_anomalies = [{"code": "sub_contract",
                              "message": "补充协议/修订合同，回款与产品明细并入主合同"}]
    status = str(base.get("orderType") or "").strip()
    record = {
        "contractNo": base.get("contractNo"),
        "contractId": cid,
        "projectName": project_name or base.get("projectName"),
        "contractAmount": amount,
        "receivedAmount": received,
        "unreceivedAmount": debt,
        "collectionRate": rate,
        "depositAmount": overview.get("depositAmount"),
        "paymentMode": overview.get("paymentMode"),
        "deliveryAmount": base.get("deliveryAmount"),
        "cargoStatus": base.get("cargoStatusStr"),
        "orderType": base.get("orderType"),
        "contractType": base.get("contractType"),
        "signTime": base.get("signTimeStr"),
        "contractStatus": status,
        "isSubContract": duplicate,
        "financialsPending": False,
        "products": products,
        "anomalies": product_anomalies,
    }
    if error:
        record["anomalies"].append({"code": "contract_detail_failed", "message": error})
    return record


def build_finance_source(client, full_payload, contract_matcher, project_ids=None, log=None):
    """以项目详情的「合同情况」为主、订单列表为兜底，组装财务数据输入。"""
    projects = (full_payload or {}).get("projects") or []
    project_ids = project_ids or {}
    wanted = []
    for proj in projects:
        for no in contract_matcher(proj):
            if no and no not in wanted:
                wanted.append(no)

    all_rows = fetch_contract_list(client)
    rows_by_name = {}
    for row in all_rows:
        rows_by_name.setdefault(str(row.get("projectName") or "").strip(), []).append(row)

    contracts_out = []
    bundle_cache = {}
    total = 0
    for proj in projects:
        name = str(proj.get("name") or "").strip()
        if not name:
            continue
        bases = []
        pid = project_ids.get(name)
        if pid:
            try:
                bases = fetch_project_contracts(client, pid)
            except Exception as exc:
                bases = []
                if log:
                    log(0, 0, "%s 项目详情的合同情况读取失败：%s" % (name, str(exc)[:120]))
        if not bases:
            # 兜底：订单列表里按项目名或项目合同编号匹配到的合同
            bases = [r for r in rows_by_name.get(name, [])
                     if any(contract_no_matches(no, str(r.get("contractNo") or "")) or
                            str(r.get("contractNo") or "") == no for no in contract_matcher(proj))]
        seen_cids = set()
        for base in bases or []:
            record = _build_record(client, name, base, bundle_cache, seen_cids)
            if not record:
                continue
            contracts_out.append(record)
            total += 1
            if log:
                log(total, 0, record["contractNo"])

    actual_nos = [str(c.get("contractNo") or "").strip() for c in contracts_out]
    unmatched = [no for no in wanted
                 if not any(contract_no_matches(no, actual) for actual in actual_nos)]
    return {
        "updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "青鸾项目合同情况 + 订单回款概况 + 报价产品",
        "contracts": contracts_out,
        "unmatchedContractNos": unmatched,
        "rawContractCount": len(all_rows),
    }


def save_source(payload, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path
