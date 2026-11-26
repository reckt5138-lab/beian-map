# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import order_source


class TestContractNoMatch(unittest.TestCase):
    def test_exact(self):
        self.assertTrue(order_source.contract_no_matches("26-01.BJ3580011Z", "26-01.BJ3580011Z"))

    def test_letter_suffix(self):
        self.assertTrue(order_source.contract_no_matches("26-01.BJ3580054Z", "26-01.BJ3580054ZA"))
        self.assertTrue(order_source.contract_no_matches("21-01.BJ1080071Z", "21-01.BJ1080071ZABDEFGHIJ..."))

    def test_not_other_contract(self):
        self.assertFalse(order_source.contract_no_matches("26-01.BJ3580054Z", "26-01.BJ3580055ZA"))
        self.assertFalse(order_source.contract_no_matches("26-01.BJ3580054Z", "26ZC0678"))


class TestProducts(unittest.TestCase):
    def test_amount_and_shipped(self):
        quotation = {"systems": [{"template": {"templateTableList": [{
            "quotationTableTupleList": [
                {"name": "烟感", "quantity": 2, "contractPrice": 100, "subtotal": 200, "cargoQuantity": 1},
                {"name": "模块", "quantity": 1, "contractPrice": 50, "subtotal": 50, "cargoQuantity": 0},
            ]}]}}]}
        products, anomalies = order_source.products_from_quotation(quotation, {})
        self.assertEqual(products[0]["amount"], 200)
        self.assertEqual(products[0]["shippedAmount"], 100)
        self.assertEqual(products[1]["shippedAmount"], 0)
        self.assertEqual(anomalies, [])


if __name__ == "__main__":
    unittest.main()
