"""Regression tests for the accepted Task 6 engineering recommendations."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from supplydesk.service import OrderService
from supplydesk.storage import JsonStore


class Task6EngineeringJudgmentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"
        self.service = OrderService(self.path)

    def test_cancelling_an_order_twice_restores_inventory_only_once(self):
        order = self.service.place_order(
            "regular", [{"product_id": "notebook", "quantity": 2}], "pickup"
        )
        initial_stock = next(
            p["stock"] for p in self.service.catalog()
            if p["product_id"] == "notebook"
        )
        self.assertEqual(initial_stock, 18)

        first_result = self.service.cancel_order(order["order_id"])
        stock_after_first_cancel = next(
            p["stock"] for p in self.service.catalog()
            if p["product_id"] == "notebook"
        )
        second_result = self.service.cancel_order(order["order_id"])
        stock_after_second_cancel = next(
            p["stock"] for p in self.service.catalog()
            if p["product_id"] == "notebook"
        )

        self.assertEqual(first_result["status"], "cancelled")
        self.assertEqual(second_result["status"], "cancelled")
        self.assertEqual(stock_after_first_cancel, 20)
        self.assertEqual(stock_after_second_cancel, 20)

    def test_json_save_replaces_state_file_and_remains_readable(self):
        store = JsonStore(self.path)
        state = store.load()
        store.save(state)

        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), state)
        self.assertEqual(list(self.path.parent.glob(".state.json.*.tmp")), [])

    def test_failed_json_serialization_preserves_previous_state(self):
        store = JsonStore(self.path)
        original = store.load()
        store.save(original)
        original_bytes = self.path.read_bytes()

        with patch("supplydesk.storage.json.dump", side_effect=TypeError("simulated write failure")):
            with self.assertRaises(TypeError):
                store.save({"not": "serializable"})

        self.assertEqual(self.path.read_bytes(), original_bytes)
        self.assertEqual(list(self.path.parent.glob(".state.json.*.tmp")), [])

    def test_cr01_exact_discount_threshold_keeps_express_fee_separate(self):
        items = [
            {"product_id": "hoodie", "quantity": 1},
            {"product_id": "notebook", "quantity": 2},
        ]
        quote = self.service.quote("student", items, "express")
        order = self.service.place_order("student", items, "express")

        self.assertEqual(quote["subtotal_cents"], 5000)
        self.assertEqual(quote["discount_cents"], 500)
        self.assertEqual(quote["delivery_cents"], 1200)
        self.assertEqual(quote["total_cents"], 5700)
        self.assertEqual(order["total_cents"], quote["total_cents"])
        self.assertEqual(order["delivery_cents"], 1200)


if __name__ == "__main__":
    unittest.main()
