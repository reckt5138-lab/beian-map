"""脱敏与发布安全检查测试：这是防止真实客户资料上网的最后一道闸门。"""

import json
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from app.security import assert_safe, district_of, load_fields, sanitize, sanitize_rows  # noqa: E402

FIXTURE = os.path.join(BASE, "tests", "fixtures", "sample_payload.json")


def load_fixture():
    with open(FIXTURE, "r", encoding="utf-8") as f:
        return json.load(f)


class TestSanitize(unittest.TestCase):
    def test_sensitive_projects_fields_are_blanked(self):
        public = sanitize(load_fixture())
        for proj in public["projects"]:
            for key in ("owner", "dept", "customer", "contact", "customerAddr",
                        "amount", "discount", "desc", "addr"):
                self.assertEqual(proj.get(key), "", "字段 %s 没有被清空" % key)
            self.assertEqual(proj.get("signs"), [])
            self.assertEqual(proj.get("signCount"), "")

    def test_public_fields_are_kept(self):
        public = sanitize(load_fixture())
        proj = public["projects"][0]
        self.assertTrue(proj["name"])
        self.assertEqual(proj["classify"], "备案项目")
        self.assertEqual(proj["lat"], 39.9)
        self.assertEqual(proj["district"], "朝阳区")

    def test_rows_only_whitelist_columns(self):
        public = sanitize(load_fixture())
        header = public["rows"][0]
        allowed = set(load_fields()["columns_keep"])
        for name in header:
            self.assertIn(name, allowed, "列 %s 不在白名单" % name)
        self.assertEqual(public["columns"], len(header))
        self.assertEqual(public["redacted"], True)
        self.assertEqual(public["count"], 3)

    def test_assert_safe_detects_leak(self):
        public = sanitize(load_fixture())
        public["projects"][0]["customer"] = "泄露的客户名"
        ok, problems = assert_safe(public)
        self.assertFalse(ok)
        self.assertIn("customer", " ".join(problems))

    def test_assert_safe_detects_signs(self):
        public = sanitize(load_fixture())
        public["projects"][0]["signs"] = [{"note": "签到"}]
        ok, problems = assert_safe(public)
        self.assertFalse(ok)

    def test_assert_safe_detects_extra_column(self):
        public = sanitize(load_fixture())
        public["rows"][0].append("业务员")
        ok, problems = assert_safe(public)
        self.assertFalse(ok)
        self.assertIn("业务员", " ".join(problems))

    def test_empty_after_sanitize_raises(self):
        payload = load_fixture()
        payload["projects"] = []
        payload["count"] = 3
        with self.assertRaises(ValueError):
            sanitize(payload)

    def test_district_extraction(self):
        self.assertEqual(district_of("北京市朝阳区建国路 88 号"), "朝阳区")
        self.assertEqual(district_of("北京市海淀区中关村大街"), "海淀区")
        self.assertEqual(district_of(""), "")

    def test_contract_and_finance_fields_blanked(self):
        payload = load_fixture()
        payload["projects"][0].update({
            "contractNo": "HT-2024-001", "contractAmount": "10000",
            "receivedAmount": "7000", "unreceivedAmount": "3000", "collectionRate": "70.00",
            "products": [{"name": "防火门", "amount": "10000"}],
        })
        public = sanitize(payload)
        proj = public["projects"][0]
        for key in ("contractNo", "contractAmount", "receivedAmount", "unreceivedAmount",
                    "collectionRate", "products", "deliveries", "shippedAmount"):
            self.assertIn(proj.get(key), ("", [], None), "财务字段 %s 未被清空" % key)
        ok, problems = assert_safe(public)
        self.assertTrue(ok, problems)

    def test_project_kind_is_kept_in_public_data(self):
        public = sanitize(load_fixture())
        for proj in public["projects"]:
            self.assertEqual(proj["pkind"], "filing")
            self.assertEqual(proj["pkindLabel"], "备案项目")

    def test_sanitize_rows_dedupes_header(self):
        rows, ncols = sanitize_rows([["项目名称", "项目名称", "业务员"], ["A", "A", "张三"]], load_fields())
        self.assertEqual(rows[0], ["项目名称"])
        self.assertEqual(ncols, 1)
        self.assertEqual(rows[1], ["A"])
