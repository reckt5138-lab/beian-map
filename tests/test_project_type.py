# -*- coding: utf-8 -*-
"""项目分类识别测试：只依据真实类型字段，不允许按名称猜测。"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from app import project_type  # noqa: E402


class TestProjectType(unittest.TestCase):
    def test_filing_by_classify(self):
        self.assertEqual(project_type.classify({"classify": "备案项目"}), "filing")

    def test_deal_by_classify(self):
        self.assertEqual(project_type.classify({"classify": "成交项目"}), "deal")
        # 接口 projectStatus 的真实取值是「成交」，不是「成交项目」
        self.assertEqual(project_type.classify({"projectStatus": "成交"}), "deal")

    def test_status_alias(self):
        self.assertEqual(project_type.classify({"projectStatus": "备案项目"}), "filing")
        self.assertEqual(project_type.classify({"status": "成交项目"}), "deal")

    def test_whitespace_and_fullwidth_space(self):
        self.assertEqual(project_type.classify({"classify": "  成交项目\u3000"}), "deal")

    def test_name_never_used_to_guess(self):
        # 名称里带“成交”但没有任何类型字段：必须 unknown
        p = {"name": "某某成交项目合同", "classify": "", "status": ""}
        self.assertEqual(project_type.classify(p), "unknown")

    def test_unknown_values_not_classified(self):
        for value in ("已成交", "备案", "签约", "中标", "其他", None, 0, "unknown"):
            self.assertEqual(project_type.classify({"classify": value}), "unknown", value)

    def test_annotate_adds_kind_and_label(self):
        rows = [{"name": "A", "classify": "备案项目"}, {"name": "B", "classify": "成交项目"},
                {"name": "C", "classify": ""}]
        project_type.annotate(rows)
        self.assertEqual([r["pkind"] for r in rows], ["filing", "deal", "unknown"])
        self.assertEqual(rows[2]["pkindLabel"], "未知类型")

    def test_ensure_kind_prefers_valid_pkind(self):
        self.assertEqual(project_type.ensure_kind({"pkind": "deal"}), "deal")

    def test_ensure_kind_recomputes_invalid_pkind(self):
        self.assertEqual(project_type.ensure_kind({"pkind": "bad", "classify": "备案项目"}), "filing")

    def test_counts(self):
        rows = [{"pkind": "filing"}, {"classify": "备案项目"}, {"classify": "成交项目"}, {}]
        self.assertEqual(project_type.counts(rows), {"filing": 2, "deal": 1, "unknown": 1})


if __name__ == "__main__":
    unittest.main()
