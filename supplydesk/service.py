"""Operations used by the command-line order desk."""

from supplydesk.storage import JsonStore


# Business-rule values are named so their meaning is clear at each use.
MIN_ORDER_QUANTITY = 1
MAX_ORDER_QUANTITY = 99
STUDENT_DISCOUNT_THRESHOLD_CENTS = 5000
STUDENT_DISCOUNT_PERCENT = 10
FREE_DELIVERY_THRESHOLD_CENTS = 10000
DELIVERY_FEE_CENTS = 600
EXPRESS_DELIVERY_FEE_CENTS = 1200
PERCENTAGE_DIVISOR = 100
DISCOUNT_ROUNDING_ADJUSTMENT = 50
ORDER_ID_WIDTH = 4


class OrderService:
    def __init__(self, state_path=".supplydesk/state.json"):
        self.store = JsonStore(state_path)

    def catalog(self):
        return self.store.load()["catalog"]

    def _build_item_lines(self, catalog, items):
        """Validate requested items and calculate their line totals."""
        if not isinstance(items, list) or not items:
            raise ValueError("An order must contain at least one item.")

        lines = []
        subtotal = 0
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Each item must contain a product_id and quantity.")

            product = next(
                (candidate for candidate in catalog
                 if candidate["product_id"] == item.get("product_id")),
                None,
            )
            if product is None:
                raise ValueError("Unknown product.")

            quantity = item.get("quantity")
            if (type(quantity) is not int
                    or quantity < MIN_ORDER_QUANTITY
                    or quantity > MAX_ORDER_QUANTITY):
                raise ValueError(
                    "Quantity must be an integer from "
                    f"{MIN_ORDER_QUANTITY} to {MAX_ORDER_QUANTITY}."
                )

            line_total = product["unit_price_cents"] * quantity
            subtotal += line_total
            lines.append({
                "product_id": product["product_id"],
                "name": product["name"],
                "unit_price_cents": product["unit_price_cents"],
                "quantity": quantity,
                "line_total_cents": line_total,
            })

        # Validate the combined quantity for each product.
        requested_quantities = {}

        for line in lines:
            product_id = line["product_id"]
            requested_quantities[product_id] = (
                requested_quantities.get(product_id, 0) + line["quantity"]
            )

        for product_id, requested_quantity in requested_quantities.items():
            product = next(
                candidate for candidate in catalog
                if candidate["product_id"] == product_id
            )

            if requested_quantity > product["stock"]:
                raise ValueError("Not enough stock for " + product_id + ".")

        return lines, subtotal

    @staticmethod
    def _calculate_discount(customer_type, subtotal):
        """Return the student discount for an eligible order."""
        if (customer_type == "student"
                and subtotal >= STUDENT_DISCOUNT_THRESHOLD_CENTS):
            return (
                subtotal * STUDENT_DISCOUNT_PERCENT + DISCOUNT_ROUNDING_ADJUSTMENT
            ) // PERCENTAGE_DIVISOR
        return 0

    @staticmethod
    def _calculate_delivery(fulfillment, subtotal, discount):
        """Return the standard delivery fee when the order is below the threshold."""
        if fulfillment == "express":
            return EXPRESS_DELIVERY_FEE_CENTS
        if (fulfillment == "delivery"
                and subtotal - discount < FREE_DELIVERY_THRESHOLD_CENTS):
            return DELIVERY_FEE_CENTS
        return 0

    def _build_quote(self, state, customer_type, items, fulfillment):
        """Build the shared pricing result used by quotes and placed orders."""
        if customer_type not in ("regular", "student"):
            raise ValueError("Customer type must be regular or student.")
        if fulfillment not in ("pickup", "delivery", "express"):
            raise ValueError("Fulfillment must be pickup, delivery, or express.")

        lines, subtotal = self._build_item_lines(state["catalog"], items)
        discount = self._calculate_discount(customer_type, subtotal)
        delivery = self._calculate_delivery(fulfillment, subtotal, discount)

        return {
            "customer_type": customer_type,
            "fulfillment": fulfillment,
            "items": lines,
            "subtotal_cents": subtotal,
            "discount_cents": discount,
            "delivery_cents": delivery,
            "total_cents": subtotal - discount + delivery,
        }

    @staticmethod
    def _deduct_inventory(catalog, items):
        """Deduct the quantities in validated order lines from the catalogue."""
        products_by_id = {product["product_id"]: product for product in catalog}
        for line in items:
            products_by_id[line["product_id"]]["stock"] -= line["quantity"]

    def quote(self, customer_type, items, fulfillment="pickup"):
        state = self.store.load()
        return self._build_quote(state, customer_type, items, fulfillment)

    def place_order(self, customer_type, items, fulfillment="pickup"):
        state = self.store.load()
        quote = self._build_quote(state, customer_type, items, fulfillment)
        order = {
            "order_id": "ORD-" + str(state["next_order_number"]).zfill(ORDER_ID_WIDTH),
            "status": "placed",
            **quote,
        }

        self._deduct_inventory(state["catalog"], quote["items"])
        state["next_order_number"] += 1
        state["orders"].append(order)
        self.store.save(state)
        return order

    def list_orders(self):
        return self.store.load()["orders"]

    def get_order(self, order_id):
        state = self.store.load()
        for order in state["orders"]:
            if order["order_id"] == order_id:
                return order
        raise ValueError("Unknown order: " + order_id)

    def cancel_order(self, order_id):
        state = self.store.load()
        order = None
        for candidate in state["orders"]:
            if candidate["order_id"] == order_id:
                order = candidate
                break
        if order is None:
            raise ValueError("Unknown order: " + order_id)
        # Cancellation is idempotent: inventory is restored only on the first call.
        if order["status"] == "cancelled":
            return order
        for line in order["items"]:
            for product in state["catalog"]:
                if product["product_id"] == line["product_id"]:
                    product["stock"] += line["quantity"]
        order["status"] = "cancelled"
        self.store.save(state)
        return order
