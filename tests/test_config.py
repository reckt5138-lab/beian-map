"""配置读取与安全处理测试。不需要网络，也不碰真实账号。"""

import json
import os
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from app.core import config as cfg_mod  # noqa: E402
from app.core.exceptions import ConfigError  # noqa: E402


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_defaults_have_required_sections(self):
        cfg = cfg_mod.load_config()
        for section in ("base_url", "crawl", "export", "publish"):
            self.assertIn(section, cfg)
        self.assertTrue(cfg["base_url"].startswith("http"))

    def test_env_overrides_credentials(self):
        os.environ["JUFA_USERNAME"] = "env_user"
        os.environ["JUFA_PASSWORD"] = "env_pass"
        cred = cfg_mod.load_credentials()
        self.assertEqual(cred["username"], "env_user")
        self.assertTrue(cred["password"].startswith("env_"))
        del os.environ["JUFA_USERNAME"]
        del os.environ["JUFA_PASSWORD"]

    def test_bad_json_message_is_chinese(self):
        bad = os.path.join(self.tmp, "bad.json")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("{not json")
        with self.assertRaises(ConfigError) as ctx:
            cfg_mod._read_json(bad)
        self.assertIn("格式错误", str(ctx.exception))

    def test_validate_config_rejects_bad_base_url(self):
        with self.assertRaises(ConfigError):
            cfg_mod.validate_config({"base_url": "ftp://x", "crawl": {}, "export": {}})

    def test_validate_config_rejects_non_positive_page_size(self):
        with self.assertRaises(ConfigError):
            cfg_mod.validate_config({"base_url": "https://a", "crawl": {"page_size": 0}, "export": {}})

    def test_mask_hides_secret(self):
        self.assertEqual(cfg_mod.mask("123456"), "***")
        self.assertTrue(cfg_mod.mask("supersecretvalue").startswith("sup"))

    def test_scrub_removes_sensitive_keys(self):
        data = {"login": {"username": "u", "password": "p"}, "publish": {"app_secret": "s"}}
        cleaned = cfg_mod.scrub(data)
        self.assertEqual(cleaned["login"]["password"], "***")
        self.assertEqual(cleaned["publish"]["app_secret"], "***")
        self.assertEqual(cleaned["login"]["username"], "u")

    def test_no_feishu_section_in_defaults(self):
        cfg = cfg_mod.load_config()
        self.assertNotIn("feishu", cfg)

    def test_defaults_have_no_plaintext_secret(self):
        cfg = cfg_mod.load_config()
        self.assertNotIn("client_secret", cfg.get("login") or {})
