# -*- coding: utf-8 -*-
"""合同与项目关联、受控产物结构测试。"""

import json
import os
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from app import contracts  # noqa: E402


def payload(*projects):
    return {"projects": [dict(p) for p in projects]}


class TestContractNumbers(unittest.TestCase):
    def test_split_multiple_nos(self):
        self.assertEqual(contracts.split_contract_nos("HT-001,HT-002；HT-003"), ["HT-001", "HT-002", "HT-003"])

    def test_split_keeps_slash_and_dash(self):
        self.assertEqual(contracts.split_contract_nos("2024/BJ-001"), ["2024/BJ-001"])

    def test_split_dedupes_and_ignores_empty(self):
        self.assertEqual(contracts.split_contract_nos("A,,A ， B"), ["A", "B"])

    def test_extract_falls_back_to_text_field(self):
        self.assertEqual(contracts.extract_contract_nos({"contractNoText": "HT-9"}), ["HT-9"])


class TestBuild(unittest.TestCase):
    def test_no_contract_project(self):
        out = contracts.build_project_contracts(payload({"name": "甲项目", "classify": "备案项目"}))
        entry = out["projects"]["甲项目"]
        self.assertEqual(entry["status"], contracts.STATUS_NO_CONTRACT)
        self.assertEqual(entry["contracts"], [])
        self.assertEqual(entry["pkind"], "filing")

    def test_source_not_configured_keeps_real_numbers_only(self):
        out = contracts.build_project_contracts(payload({"name": "甲", "contractNo": "HT-001,HT-002"}))
        entry = out["projects"]["甲"]
        self.assertEqual(entry["status"], contracts.STATUS_NO_SOURCE)
        self.assertEqual([c["contractNo"] for c in entry["contracts"]], ["HT-001", "HT-002"])
        self.assertTrue(all(c["contractAmount"] is None for c in entry["contracts"]))
        self.assertTrue(out["restricted"])

    def test_finance_matched_computes_amounts(self):
        source = {"updated": "2026-11-25", "contracts": [{
            "contractNo": "HT-001", "projectName": "甲", "contractAmount": "10000",
            "receipts": [{"amount": 6000, "status": "有效"}],
            "products": [{"name": "防火门", "amount": "10000", "deliveries": [{"amount": 4000}]}],
        }]}
        entry = contracts.build_project_contracts(payload({"name": "甲", "contractNo": "HT-001"}), source)["projects"]["甲"]
        self.assertEqual(entry["status"], contracts.STATUS_OK)
        c = entry["contracts"][0]
        self.assertEqual(c["receivedAmount"], "6,000.00")
        self.assertEqual(c["unreceivedAmount"], "4,000.00")
        self.assertEqual(c["collectionRate"], "60.00")
        self.assertEqual(c["totalShippedAmount"], "4,000.00")

    def test_no_finance_record_is_distinct(self):
        source = {"contracts": []}
        entry = contracts.build_project_contracts(payload({"name": "甲", "contractNo": "HT-001"}), source)["projects"]["甲"]
        self.assertEqual(entry["status"], contracts.STATUS_NO_RECORD)
        self.assertEqual(entry["contracts"][0]["contractAmount"], None)

    def test_multi_contract_project(self):
        source = {"contracts": [
            {"contractNo": "HT-1", "contractAmount": "1000", "receipts": [{"amount": 1000}]},
            {"contractNo": "HT-2", "contractAmount": "2000", "receipts": []},
        ]}
        entry = contracts.build_project_contracts(payload({"name": "甲", "contractNo": "HT-1,HT-2"}), source)["projects"]["甲"]
        self.assertEqual(len(entry["contracts"]), 2)
        self.assertEqual(entry["summary"]["contractAmount"], "3,000.00")
        self.assertEqual(entry["summary"]["receivedAmount"], "1,000.00")

    def test_bad_finance_file_rejected(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"items": []}, f)
            path = f.name
        try:
            with self.assertRaises(ValueError):
                contracts.load_finance_source(path)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
