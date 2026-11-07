"""Generated with ChatGPT GPT-6"""

from pathlib import Path
import tempfile
import unittest

from supplydesk.service import OrderService


class OrderServiceSafetyNetTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"
        self.service = OrderService(self.path)

    def test_regular_delivery_below_free_delivery_threshold(self):
        quote = self.service.quote(
            "regular", [{"product_id": "notebook", "quantity": 2}], "delivery"
        )
        self.assertEqual(quote["subtotal_cents"], 1000)
        self.assertEqual(quote["discount_cents"], 0)
        self.assertEqual(quote["delivery_cents"], 600)
        self.assertEqual(quote["total_cents"], 1600)

    def test_student_discount_applies_at_exact_5000_cent_boundary(self):
        quote = self.service.quote(
            "student", [{"product_id": "hoodie", "quantity": 1},
                        {"product_id": "notebook", "quantity": 2}], "pickup"
        )
        self.assertEqual(quote["subtotal_cents"], 5000)
        self.assertEqual(quote["discount_cents"], 500)
        self.assertEqual(quote["total_cents"], 4500)

    def test_invalid_request_does_not_change_saved_state(self):
        invalid_requests = [
            ("guest", [{"product_id": "notebook", "quantity": 1}], "pickup"),
            ("regular", [{"product_id": "notebook", "quantity": 0}], "pickup"),
            ("regular", [{"product_id": "missing", "quantity": 1}], "pickup"),
            ("regular", [{"product_id": "notebook", "quantity": 1}], "courier"),
        ]
        for customer, items, fulfillment in invalid_requests:
            with self.subTest(customer=customer, items=items, fulfillment=fulfillment):
                with self.assertRaises(ValueError):
                    self.service.place_order(customer, items, fulfillment)
                self.assertFalse(self.path.exists())
                self.assertEqual(self.service.catalog()[0]["stock"], 20)
                self.assertEqual(self.service.list_orders(), [])

    def test_quote_matches_placed_order_and_history_survives_reopen_and_cancel(self):
        items = [{"product_id": "hoodie", "quantity": 2}]
        quote = self.service.quote("student", items, "delivery")
        order = self.service.place_order("student", items, "delivery")
        for key in ("customer_type", "fulfillment", "items", "subtotal_cents",
                    "discount_cents", "delivery_cents", "total_cents"):
            self.assertEqual(order[key], quote[key])
        self.assertEqual(order["order_id"], "ORD-0001")

        reopened = OrderService(self.path)
        self.assertEqual(reopened.get_order("ORD-0001"), order)
        stock_after_placement = next(
            p["stock"] for p in reopened.catalog() if p["product_id"] == "hoodie"
        )
        self.assertEqual(stock_after_placement, 3)

        cancelled = reopened.cancel_order("ORD-0001")
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["items"], order["items"])
        self.assertEqual(cancelled["total_cents"], order["total_cents"])
        self.assertEqual(
            next(p["stock"] for p in reopened.catalog() if p["product_id"] == "hoodie"),
            5,
        )
        self.assertEqual(reopened.list_orders(), [cancelled])


if __name__ == "__main__":
    unittest.main()
