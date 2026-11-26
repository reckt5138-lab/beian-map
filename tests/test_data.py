"""数据校验与原子写入测试。"""

import json
import os
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from app.data import atomic
from app.data.validate import validate  # noqa: E402

FIXTURE = os.path.join(BASE, "tests", "fixtures", "sample_payload.json")


def load_fixture():
    with open(FIXTURE, "r", encoding="utf-8") as f:
        return json.load(f)


class TestValidate(unittest.TestCase):
    def test_sample_passes(self):
        ok, report = validate(load_fixture())
        self.assertTrue(ok, report["problems"])
        self.assertEqual(report["count"], 3)

    def test_empty_rejected(self):
        payload = load_fixture()
        payload["projects"] = []
        payload["rows"] = [payload["rows"][0]]
        payload["count"] = 0
        ok, report = validate(payload)
        self.assertFalse(ok)
        self.assertIn("0 条", " ".join(report["problems"]))

    def test_duplicate_names_rejected(self):
        payload = load_fixture()
        payload["projects"][1]["name"] = payload["projects"][0]["name"]
        ok, report = validate(payload)
        self.assertFalse(ok)
        self.assertIn("重复", " ".join(report["problems"]))

    def test_bad_date_rejected(self):
        payload = load_fixture()
        payload["projects"][0]["filing"] = "2026/08/01"
        ok, report = validate(payload, allow_empty=False)
        self.assertFalse(ok)

    def test_drop_is_blocked(self):
        payload = load_fixture()
        payload["projects"] = payload["projects"][:1]
        payload["count"] = 1
        ok, report = validate(payload, previous={"count": 18})
        self.assertFalse(ok)
        self.assertIn("异常下降", " ".join(report["problems"]))

    def test_count_mismatch_rejected(self):
        payload = load_fixture()
        payload["count"] = 99
        ok, report = validate(payload)
        self.assertFalse(ok)

    def test_incomplete_pagination_rejected(self):
        payload = load_fixture()
        payload["crawl_pages"] = 5
        payload["crawl_pages_done"] = 3
        ok, report = validate(payload)
        self.assertFalse(ok)
        self.assertIn("分页未完成", " ".join(report["problems"]))

    def test_bad_coord_is_warning_only(self):
        payload = load_fixture()
        payload["projects"][0]["lat"] = 999
        ok, report = validate(payload)
        self.assertTrue(ok)
        self.assertTrue(report["warnings"])


class TestAtomic(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_atomic_json_roundtrip(self):
        path = os.path.join(self.tmp, "d.json")
        atomic.atomic_write_json(path, {"a": 1})
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["a"], 1)
        self.assertEqual([f for f in os.listdir(self.tmp) if f.startswith(".tmp_")], [])

    def test_backup_keeps_original(self):
        path = os.path.join(self.tmp, "x.json")
        atomic.atomic_write_json(path, {"a": 1})
        bak = atomic.backup_file(path, os.path.join(self.tmp, "bk"))
        self.assertTrue(os.path.exists(bak))
        self.assertTrue(os.path.exists(path))

