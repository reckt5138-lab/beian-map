"""地图构建测试：离线用样本数据构建一版页面，检查产物与自检逻辑。"""

import json
import os
import shutil
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from app.map import build_page as build_page_fn  # noqa: E402
from app.map import copy_to_dist, verify
from app.security import sanitize  # noqa: E402

FIXTURE = os.path.join(BASE, "tests", "fixtures", "sample_payload.json")


class TestMapBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        with open(FIXTURE, "r", encoding="utf-8") as f:
            payload = sanitize(json.load(f))
        cls.data_path = os.path.join(cls.tmp, "data.json")
        with open(cls.data_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_build_produces_html_with_snapshot(self):
        out = os.path.join(self.tmp, "index.html")
        ok, msg = build_page_fn(from_json=self.data_path, out=out)
        self.assertTrue(ok, msg)
        self.assertTrue(os.path.getsize(out) > 20000)
        with open(out, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("window.EMBEDDED", text)
        self.assertIn("示例小区 A 区改造工程", text)
        # 脱敏字段不能出现在页面里
        self.assertNotIn("13800000001", text)
        self.assertNotIn("示例客户甲", text)

    def test_verify_rejects_credential_leak(self):
        bad = os.path.join(self.tmp, "bad.html")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("<html>" + "x" * 30000 + 'ghp_abcdefghijklmnopqrstuvwxyz123456</html>')
        ok, msg = verify(bad)
        self.assertFalse(ok)
        self.assertIn("凭证", msg)

    def test_verify_rejects_missing_file(self):
        ok, msg = verify(os.path.join(self.tmp, "nope.html"))
        self.assertFalse(ok)
        self.assertIn("不存在", msg)

    def test_copy_to_dist_only_two_files(self):
        dist = os.path.join(self.tmp, "dist")
        src_html = os.path.join(self.tmp, "index.html")
        build_page_fn(from_json=self.data_path, out=src_html)
        copy_to_dist(src_html, self.data_path, dist)
        self.assertEqual(sorted(os.listdir(dist)), ["data.json", "index.html"])


