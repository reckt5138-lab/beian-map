"""采集解析测试（离线）：矩阵 → payload 的字段映射，不连青鸾接口。

注意：真实登录/抓取属于「未完成真实接口验证」，这里只验证解析层与字段映射，
不冒充真实抓取成功。
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "app"))

MATRIX = [
    ["项目名称", "项目地址", "业务员", "客户信息", "备案时间", "项目进度", "项目类型"],
    ["示例小区 A 区改造工程", "北京市朝阳区示例路 1 号", "张三", "示例客户甲", "2026-08-01", "封顶", "民商用/住宅"],
    ["示例园区 B 号楼", "北京市海淀区示例路 2 号", "李四", "示例客户乙", "2026-09-10", "主体", "民商用/商业"],
]


class TestCrawlStatusFilter(unittest.TestCase):
    """接口 projectStatus 实际取值是「成交」，Tab 文案是「成交项目」，必须做别名展开。"""

    def setUp(self):
        from app import crawler
        self.crawler = crawler

    def test_deal_alias_expanded(self):
        values = self.crawler.expand_status_filter(["备案项目", "成交项目"])
        self.assertIn("备案项目", values)
        self.assertIn("成交", values)

    def test_filter_keeps_filing_and_deal(self):
        rows = [{"projectStatus": "备案项目"}, {"projectStatus": "成交"},
                {"projectStatus": "失效"}, {"projectStatus": "丢失"}, {"projectStatus": "非备案人报价项目"}]
        kept, dropped = self.crawler.filter_rows_by_status(rows, ["备案项目", "成交项目"])
        self.assertEqual([r["projectStatus"] for r in kept], ["备案项目", "成交"])
        self.assertEqual(sum(dropped.values()), 3)

    def test_empty_filter_keeps_all(self):
        rows = [{"projectStatus": "失效"}]
        kept, dropped = self.crawler.filter_rows_by_status(rows, [])
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, {})


class TestMatrixToKind(unittest.TestCase):
    def test_status_column_sets_project_kind(self):
        from app import matrix_parse
        matrix = [
            ["项目名称", "项目状态"],
            ["备案甲", "备案项目"],
            ["成交乙", "成交"],
            ["未知丙", ""],
        ]
        projects, _ = matrix_parse.parse(matrix)
        self.assertEqual([p["pkind"] for p in projects], ["filing", "deal", "unknown"])


class TestCrawlerParse(unittest.TestCase):
    def test_matrix_to_payload_keeps_fields(self):
        import map_payload
        payload = map_payload.from_matrix(MATRIX, 7, source="test", updated="2026-11-21 02:10:00")
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["columns"], 7)
        names = [p["name"] for p in payload["projects"]]
        self.assertIn("示例小区 A 区改造工程", names)
        self.assertTrue(all("lat" in p and "lng" in p for p in payload["projects"]))

    def test_matrix_without_header_raises(self):
        import map_payload
        with self.assertRaises(RuntimeError):
            map_payload.from_matrix([["编号", "备注"], ["x", "y"]], 2)

    def test_save_is_idempotent(self):
        import json
        import shutil
        import tempfile
        import map_payload
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, "d.json")
            payload = map_payload.from_matrix(MATRIX, 7)
            wrote1, changed1 = map_payload.save(payload, path)
            wrote2, changed2 = map_payload.save(payload, path)
            self.assertTrue(wrote1 and changed1)
            self.assertFalse(wrote2 or changed2, "重复写入应判定为无变化")
            with open(path, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["count"], 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_generated_at_not_counted_as_change(self):
        import map_payload
        a = {"count": 2, "generated_at": "2026-11-21T00:00:00+08:00"}
        b = {"count": 2, "generated_at": "2026-11-22T00:00:00+08:00"}
        self.assertEqual(map_payload.core(a), map_payload.core(b))
