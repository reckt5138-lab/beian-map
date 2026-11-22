"""地图页面测试：产物必须是单一数据源（./data.json）、无旧数据源残留。"""

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

    def test_build_only_fetches_local_data_json(self):
        out = os.path.join(self.tmp, "index.html")
        ok, msg = build_page_fn(from_json=self.data_path, out=out)
        self.assertTrue(ok, msg)
        self.assertTrue(os.path.getsize(out) > 20000)
        with open(out, encoding="utf-8") as f:
            text = f.read()
        # 唯一数据源
        self.assertIn("const DATA_URL = './data.json'", text)
        self.assertNotIn("raw.githubusercontent", text)
        self.assertNotIn("jsdelivr.net/gh/", text)
        self.assertNotIn("feishu", text.lower())
        self.assertNotIn("window.EMBEDDED", text)
        self.assertNotIn("localStorage", text)

    def test_page_has_error_message_for_failure(self):
        out = os.path.join(self.tmp, "index.html")
        build_page_fn(from_json=self.data_path, out=out)
        with open(out, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("云端数据加载失败，请稍后刷新页面。", text)

    def test_page_does_not_embed_project_data(self):
        out = os.path.join(self.tmp, "index.html")
        build_page_fn(from_json=self.data_path, out=out)
        with open(out, encoding="utf-8") as f:
            text = f.read()
        # 页面不再内嵌业务数据，样本项目名与脱敏字段都不应出现在 HTML 里
        self.assertNotIn("示例小区 A 区改造工程", text)
        self.assertNotIn("13800000001", text)
        self.assertNotIn("示例客户甲", text)

    def test_verify_rejects_credential_leak(self):
        bad = os.path.join(self.tmp, "bad.html")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("<html>./data.json" + "x" * 30000 + 'ghp_abcdefghijklmnopqrstuvwxyz123456</html>')
        ok, msg = verify(bad)
        self.assertFalse(ok)
        self.assertIn("凭证", msg)

    def test_verify_rejects_old_data_source(self):
        bad = os.path.join(self.tmp, "old.html")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("<html>./data.json" + "x" * 30000 + "raw.githubusercontent.com</html>")
        ok, msg = verify(bad)
        self.assertFalse(ok)
        self.assertIn("旧数据源", msg)

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
