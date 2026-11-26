# -*- coding: utf-8 -*-
"""合同金额 / 回款 / 发货金额的精确计算测试（Decimal，两位小数）。"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from app import finance  # noqa: E402


def contract(**kw):
    base = {"contractNo": "HT-001", "contractAmount": "10000", "receipts": [], "products": []}
    base.update(kw)
    return base


class TestParseAndFormat(unittest.TestCase):
    def test_parse_currency_text(self):
        self.assertEqual(finance.parse_amount("¥10,000.00")[0], finance.Decimal("10000.00"))
        self.assertEqual(finance.parse_amount("10000.5")[0], finance.Decimal("10000.5"))

    def test_parse_empty_and_invalid(self):
        self.assertEqual(finance.parse_amount("")[0], None)
        self.assertEqual(finance.parse_amount(None)[0], None)
        self.assertEqual(finance.parse_amount("abc")[1], "invalid")

    def test_money_text_two_decimals_and_thousands(self):
        self.assertEqual(finance.money_text(finance.Decimal("1234.5")), "1,234.50")
        self.assertIsNone(finance.money_text(None))


class TestReceipts(unittest.TestCase):
    def test_single_receipt(self):
        c = finance.compute_contract(contract(contractAmount="10000",
                                              receipts=[{"amount": "7000", "status": "已回款"}]))
        self.assertEqual(c["contractAmount"], "10,000.00")
        self.assertEqual(c["receivedAmount"], "7,000.00")
        self.assertEqual(c["unreceivedAmount"], "3,000.00")
        self.assertEqual(c["collectionRate"], "70.00")

    def test_multiple_receipts_accumulate(self):
        c = finance.compute_contract(contract(receipts=[{"amount": 3000}, {"amount": "4000.50"}]))
        self.assertEqual(c["receivedAmount"], "7,000.50")
        self.assertEqual(c["unreceivedAmount"], "2,999.50")
        self.assertEqual(c["collectionRate"], "70.01")

    def test_void_and_refund_excluded(self):
        receipts = [{"amount": 5000, "status": "有效"},
                    {"amount": 5000, "status": "作废"}, {"amount": 2000, "status": "退款"},
                    {"amount": -1000, "status": "冲销"}]
        total, included, excluded, anoms = finance.sum_receipts(receipts)
        self.assertEqual(total, finance.Decimal("5000"))
        self.assertEqual((included, excluded), (1, 3))
        self.assertTrue(any(a["code"] == "receipts_excluded" for a in finance.compute_contract(contract(receipts=receipts))["anomalies"]))

    def test_no_receipts_means_zero_with_anomaly(self):
        c = finance.compute_contract(contract(receipts=None))
        self.assertEqual(c["receivedAmount"], "0.00")
        self.assertTrue(any(a["code"] == "receipts_missing" for a in c["anomalies"]))

    def test_zero_contract_amount_no_division_error(self):
        c = finance.compute_contract(contract(contractAmount="0", receipts=[{"amount": 0}]))
        self.assertIsNone(c["collectionRate"])
        self.assertEqual(c["unreceivedAmount"], "0.00")
        self.assertTrue(any(a["code"] == "contract_amount_zero" for a in c["anomalies"]))

    def test_empty_contract_amount(self):
        c = finance.compute_contract(contract(contractAmount=""))
        self.assertIsNone(c["contractAmount"])
        self.assertIsNone(c["unreceivedAmount"])
        self.assertIsNone(c["collectionRate"])
        self.assertTrue(any(a["code"] == "contract_amount_missing" for a in c["anomalies"]))

    def test_received_exceeds_contract_kept_as_anomaly(self):
        c = finance.compute_contract(contract(contractAmount="10000", receipts=[{"amount": 12000}]))
        self.assertEqual(c["unreceivedAmount"], "-2,000.00")
        self.assertEqual(c["collectionRate"], "120.00")
        self.assertTrue(any(a["code"] == "received_exceeds_contract" for a in c["anomalies"]))


class TestProducts(unittest.TestCase):
    def test_multiple_products_and_totals(self):
        c = finance.compute_contract(contract(products=[
            {"name": "防火门", "amount": "1000", "shippedAmount": "800"},
            {"name": "卷帘", "amount": "2000", "shippedAmount": "1500"},
        ]))
        self.assertEqual([r["seq"] for r in c["products"]], [1, 2])
        self.assertEqual(c["totalContractAmount"], "3,000.00")
        self.assertEqual(c["totalShippedAmount"], "2,300.00")

    def test_multiple_deliveries_accumulate(self):
        c = finance.compute_contract(contract(products=[{
            "name": "钢质门", "amount": "1000",
            "deliveries": [{"amount": 300}, {"amount": 250}, {"amount": 100, "status": "作废"}],
        }]))
        self.assertEqual(c["products"][0]["shippedAmount"], "550.00")
        self.assertEqual(c["totalShippedAmount"], "550.00")

    def test_partial_shipment_and_missing_delivery(self):
        c = finance.compute_contract(contract(products=[
            {"name": "A", "amount": "500", "shippedAmount": "200"},
            {"name": "B", "amount": "500"},
        ]))
        self.assertEqual(c["products"][1]["shippedAmount"], None)
        self.assertEqual(c["totalShippedAmount"], "200.00")
        self.assertTrue(c["productsIncomplete"])
        self.assertTrue(any(a["code"] == "delivery_missing" for a in c["anomalies"]))

    def test_missing_product_amount(self):
        c = finance.compute_contract(contract(products=[{"name": "A", "shippedAmount": "100"}]))
        self.assertIsNone(c["products"][0]["contractAmount"])
        self.assertIsNone(c["totalContractAmount"])
        self.assertTrue(any(a["code"] == "product_amount_missing" for a in c["anomalies"]))

    def test_no_products(self):
        c = finance.compute_contract(contract(products=[]))
        self.assertEqual(c["products"], [])
        self.assertIsNone(c["totalContractAmount"])
        self.assertIsNone(c["totalShippedAmount"])

    def test_product_without_name_skipped_with_anomaly(self):
        c = finance.compute_contract(contract(products=[{"name": " ", "amount": "100"}]))
        self.assertEqual(c["products"], [])
        self.assertTrue(any(a["code"] == "product_name_missing" for a in c["anomalies"]))


class TestContractsSummary(unittest.TestCase):
    def test_multi_contract_summary(self):
        result = finance.compute_contracts([
            {"contractNo": "HT-1", "contractAmount": "1000", "receipts": [{"amount": 600}]},
            {"contractNo": "HT-2", "contractAmount": "2000", "receipts": [{"amount": 1500}]},
        ])
        self.assertEqual(result["summary"]["contractAmount"], "3,000.00")
        self.assertEqual(result["summary"]["receivedAmount"], "2,100.00")
        self.assertEqual(result["summary"]["unreceivedAmount"], "900.00")
        self.assertEqual(result["summary"]["collectionRate"], "70.00")

    def test_summary_with_zero_total(self):
        result = finance.compute_contracts([{"contractNo": "HT-1", "contractAmount": "0"}])
        self.assertIsNone(result["summary"]["collectionRate"])


class TestNoFinanceInPublic(unittest.TestCase):
    def test_blank_placeholder_keys_are_accepted(self):
        payload = {"projects": [{"name": "A", "contractNo": "", "contractAmount": "", "pkind": "filing"}],
                   "rows": [["项目名称", "项目分类"]]}
        ok, problems = finance.assert_no_finance(payload)
        self.assertTrue(ok, problems)

    def test_valued_finance_fields_are_rejected(self):
        payload = {"projects": [{"name": "A", "contractNo": "HT-001", "contractAmount": "10000"}],
                   "rows": [["项目名称", "合同金额"]]}
        ok, problems = finance.assert_no_finance(payload)
        self.assertFalse(ok)
        self.assertTrue(any("contractNo" in p for p in problems))
        self.assertTrue(any("合同金额" in p for p in problems))

    def test_finance_container_keys_rejected(self):
        payload = {"projects": [{"name": "A", "receipts": [{"amount": 1}]}], "rows": [["项目名称"]]}
        ok, _ = finance.assert_no_finance(payload)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
