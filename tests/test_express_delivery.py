"""Acceptance tests for CR-01 Express Delivery."""

import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from supplydesk.cli import build_parser, main
from supplydesk.menu import run_menu
from supplydesk.service import OrderService


class ExpressDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"
        self.service = OrderService(self.path)

    def test_regular_express_quote_adds_fixed_1200_cent_fee(self):
        quote = self.service.quote(
            "regular", [{"product_id": "notebook", "quantity": 2}], "express"
        )
        self.assertEqual(quote["subtotal_cents"], 1000)
        self.assertEqual(quote["discount_cents"], 0)
        self.assertEqual(quote["delivery_cents"], 1200)
        self.assertEqual(quote["total_cents"], 2200)

    def test_student_express_discount_applies_to_merchandise_only(self):
        quote = self.service.quote(
            "student", [{"product_id": "hoodie", "quantity": 2}], "express"
        )
        self.assertEqual(quote["subtotal_cents"], 8000)
        self.assertEqual(quote["discount_cents"], 800)
        self.assertEqual(quote["delivery_cents"], 1200)
        self.assertEqual(quote["total_cents"], 8400)

    def test_express_is_not_waived_when_standard_delivery_is_free(self):
        items = [{"product_id": "hoodie", "quantity": 3}]
        standard = self.service.quote("regular", items, "delivery")
        express = self.service.quote("regular", items, "express")
        self.assertEqual(standard["delivery_cents"], 0)
        self.assertEqual(standard["total_cents"], 12000)
        self.assertEqual(express["delivery_cents"], 1200)
        self.assertEqual(express["total_cents"], 13200)

    def test_express_order_quote_reopen_history_and_cancel_preserve_details(self):
        items = [{"product_id": "hoodie", "quantity": 2}]
        quote = self.service.quote("student", items, "express")
        order = self.service.place_order("student", items, "express")
        for field in ("customer_type", "fulfillment", "items", "subtotal_cents",
                      "discount_cents", "delivery_cents", "total_cents"):
            self.assertEqual(order[field], quote[field])

        reopened = OrderService(self.path)
        self.assertEqual(reopened.get_order(order["order_id"]), order)
        self.assertEqual(reopened.list_orders(), [order])
        cancelled = reopened.cancel_order(order["order_id"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["fulfillment"], "express")
        self.assertEqual(cancelled["items"], order["items"])
        self.assertEqual(cancelled["delivery_cents"], 1200)
        self.assertEqual(cancelled["discount_cents"], 800)
        self.assertEqual(cancelled["total_cents"], 8400)

    def test_cli_accepts_express_and_rejects_other_fulfillment_values(self):
        args = build_parser().parse_args([
            "quote", "--customer", "student", "--fulfillment", "express",
            "--item", "hoodie:2",
        ])
        self.assertEqual(args.fulfillment, "express")
        with self.assertRaises(SystemExit):
            build_parser().parse_args([
                "quote", "--fulfillment", "overnight", "--item", "hoodie:1"
            ])

    def test_individual_place_command_creates_express_order(self):
        output = StringIO()
        with redirect_stdout(output):
            status = main([
                "--data", str(self.path), "place", "--customer", "student",
                "--fulfillment", "express", "--item", "hoodie:2",
            ])
        self.assertEqual(status, 0)
        order = json.loads(output.getvalue())
        self.assertEqual(order["fulfillment"], "express")
        self.assertEqual(order["delivery_cents"], 1200)
        self.assertEqual(order["total_cents"], 8400)
        self.assertEqual(self.service.get_order(order["order_id"]), order)

    def test_regular_pickup_defaults_are_unchanged(self):
        args = build_parser().parse_args(["quote", "--item", "notebook:1"])
        self.assertEqual(args.customer, "regular")
        self.assertEqual(args.fulfillment, "pickup")

    def test_interactive_menu_accepts_express(self):
        answers = iter(["2", "student", "hoodie", "2", "", "express", "0"])
        output = StringIO()

        def fake_input(prompt=""):
            output.write(prompt)
            return next(answers)

        with patch("builtins.input", side_effect=fake_input), redirect_stdout(output):
            run_menu(self.service)
        rendered = output.getvalue()
        self.assertIn("Fulfillment: express", rendered)
        self.assertIn("Delivery: $12.00", rendered)
        self.assertIn("Total: $84.00", rendered)
        self.assertIn("Fulfillment [pickup/delivery/express]", rendered)

    def test_exact_student_discount_threshold_remains_eligible(self):
        quote = self.service.quote(
            "student", [{"product_id": "hoodie", "quantity": 1},
                        {"product_id": "notebook", "quantity": 2}], "pickup"
        )
        self.assertEqual(quote["subtotal_cents"], 5000)
        self.assertEqual(quote["discount_cents"], 500)
        self.assertEqual(quote["total_cents"], 4500)


if __name__ == "__main__":
    unittest.main()
