"""Order lifecycle: server-side pricing, the status machine and delivery.

Status machine (proposal section 4.3):

    pending_payment -> paid | expired | cancelled
    paid            -> processing | refunded
    processing      -> delivered | delivery_failed
    delivered       -> refunded
    delivery_failed -> processing | refunded
"""
from __future__ import annotations

import secrets
from datetime import timedelta

from .. import clock
from ..db import execute, get_db, query
from . import catalog, coupons, payments, suppliers

ALLOWED_TRANSITIONS = {
    "pending_payment": {"paid", "expired", "cancelled"},
    "paid": {"processing", "refunded"},
    "processing": {"delivered", "delivery_failed"},
    "delivered": {"refunded"},
    "delivery_failed": {"processing", "refunded"},
    "expired": set(),
    "cancelled": set(),
    "refunded": set(),
}

REVENUE_STATUSES = ("paid", "processing", "delivered")


class OrderError(Exception):
    """Raised with a message intended for the customer or the operator."""


def new_order_no() -> str:
    return f"EL{clock.now().strftime('%y%m%d')}{secrets.token_hex(3).upper()}"


def get(order_no: str):
    return query("SELECT * FROM orders WHERE order_no = ?", ((order_no or "").strip().upper(),),
                 one=True)


def history(order_id: int) -> list:
    return query("SELECT * FROM order_history WHERE order_id = ? ORDER BY id", (order_id,))


def record_history(order_id: int, old: str | None, new: str, actor: str, note: str = "") -> None:
    execute(
        "INSERT INTO order_history (order_id, old_status, new_status, actor, note, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (order_id, old, new, actor, note, clock.iso()),
    )


def transition(order, new_status: str, actor: str = "system", note: str = "") -> dict:
    """Move an order to a new status, rejecting transitions the model forbids."""
    old_status = order["status"]
    if new_status == old_status:
        return dict(order)
    if new_status not in ALLOWED_TRANSITIONS.get(old_status, set()):
        raise OrderError(f"Cannot change status from {old_status} to {new_status}.")
    execute(
        "UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
        (new_status, clock.iso(), order["id"]),
    )
    record_history(order["id"], old_status, new_status, actor, note)
    return dict(query("SELECT * FROM orders WHERE id = ?", (order["id"],), one=True))


# --------------------------------------------------------------------------- creation
def create_order(*, game_slug: str, product_id: int, player_id: str, server: str = "",
                 coupon_code: str = "", player_name: str = "", actor: str = "customer") -> dict:
    """Create an order priced entirely from the database."""
    game = catalog.get_game(game_slug)
    if not game or not game["active"]:
        raise OrderError("Please choose a game.")

    product = catalog.get_product(int(product_id or 0))
    if not product or not product["active"]:
        raise OrderError("Please choose a product.")
    if product["game_id"] != game["id"]:
        raise OrderError("That product does not belong to the selected game.")

    player_id = (player_id or "").strip()
    if not player_id:
        raise OrderError("Please enter your Player ID.")
    if game["server_type"] == "select" and server not in game["servers"]:
        raise OrderError("Please choose a server.")
    if game["server_type"] == "text" and not server.strip():
        raise OrderError("Please enter the server.")

    subtotal = product["price_cents"]
    discount = 0
    code = ""
    if coupon_code:
        try:
            coupon, discount = coupons.apply(coupon_code, subtotal)
            code = coupon["code"]
        except coupons.CouponError as exc:
            raise OrderError(str(exc)) from exc

    if not player_name:
        try:
            info = suppliers.get_supplier().lookup_player(game["slug"], player_id, server)
            player_name = info.nickname
        except suppliers.PlayerNotFound as exc:
            raise OrderError(str(exc)) from exc

    total = subtotal - discount
    now = clock.now()
    order_no = new_order_no()
    order_id = execute(
        """INSERT INTO orders
           (order_no, game_id, product_id, item_title, player_id, server, player_name,
            subtotal_cents, discount_cents, total_cents, coupon_code, status, expires_at,
            created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (order_no, game["id"], product["id"], product["title"], player_id, server, player_name,
         subtotal, discount, total, code or None, "pending_payment",
         clock.iso(now + timedelta(minutes=10)), clock.iso(now), clock.iso(now)),
    )
    if code:
        coupons.consume(code)
    record_history(order_id, None, "pending_payment", actor, "Order created")

    order = dict(query("SELECT * FROM orders WHERE id = ?", (order_id,), one=True))
    charge = payments.get_provider().create(order)
    execute(
        "INSERT INTO payments (order_id, qr_reference, qr_payload, amount_cents, currency, status, "
        "created_at) VALUES (?,?,?,?,?,?,?)",
        (order_id, charge.reference, charge.payload, charge.amount_cents, charge.currency,
         "pending", clock.iso()),
    )
    order["qr_payload"] = charge.payload
    return order


def latest_payment(order_id: int):
    return query(
        "SELECT * FROM payments WHERE order_id = ? ORDER BY id DESC LIMIT 1", (order_id,), one=True
    )


# --------------------------------------------------------------------------- payment + delivery
def expire_if_stale(order) -> dict:
    if order["status"] == "pending_payment" and clock.parse(order["expires_at"]) < clock.now():
        return transition(order, "expired", "system", "QR code expired")
    return dict(order)


def settle(order) -> dict:
    """Ask the provider about the pending payment, then deliver if it is confirmed."""
    order = expire_if_stale(order)
    if order["status"] != "pending_payment":
        return order

    payment = latest_payment(order["id"])
    if payment is None:
        return order

    result = payments.get_provider().poll(payment["qr_reference"])
    if result.status != "paid":
        return order

    # amount, currency and reference must all match (proposal FR-P04)
    if result.amount_cents != order["total_cents"] or result.currency != payment["currency"]:
        execute("UPDATE payments SET status = 'mismatch', provider_txn_id = ? WHERE id = ?",
                (result.txn_id or f"MISMATCH{payment['id']}", payment["id"]))
        record_history(order["id"], order["status"], order["status"], "system",
                       f"Payment mismatch: expected {order['total_cents']}, "
                       f"got {result.amount_cents}")
        return dict(order)

    duplicate = query(
        "SELECT id FROM payments WHERE provider_txn_id = ? AND id <> ?",
        (result.txn_id, payment["id"]), one=True,
    )
    if duplicate:
        execute("UPDATE payments SET status = 'mismatch' WHERE id = ?", (payment["id"],))
        return dict(order)

    execute(
        "UPDATE payments SET status = 'confirmed', provider_txn_id = ?, confirmed_at = ? WHERE id = ?",
        (result.txn_id, clock.iso(), payment["id"]),
    )
    order = transition(order, "paid", "system", f"Payment {result.txn_id} confirmed")
    return deliver(order)


def deliver(order, actor: str = "system") -> dict:
    """Send the top-up to the supplier, retrying up to DELIVERY_MAX_ATTEMPTS."""
    from flask import current_app

    order = transition(order, "processing", actor, "Top-up request sent to supplier")
    supplier = suppliers.get_supplier()
    attempts = current_app.config["DELIVERY_MAX_ATTEMPTS"]

    for attempt in range(1, attempts + 1):
        view = dict(order)
        view["_attempt"] = attempt
        result = supplier.deliver(view)
        execute(
            "INSERT INTO supplier_requests (order_id, attempt, result, supplier_ref, message, "
            "created_at) VALUES (?,?,?,?,?,?)",
            (order["id"], attempt, "success" if result.ok else "failed", result.supplier_ref,
             result.message, clock.iso()),
        )
        if result.ok:
            return transition(order, "delivered", actor, result.message)

    return transition(order, "delivery_failed", actor,
                      f"Supplier failed after {attempts} attempts")


def retry_delivery(order, actor: str) -> dict:
    if order["status"] != "delivery_failed":
        raise OrderError("Only a failed order can be retried.")
    return deliver(dict(order), actor)


def cancel(order, actor: str, note: str = "Cancelled by operator") -> dict:
    if order["status"] != "pending_payment":
        raise OrderError("Only an unpaid order can be cancelled.")
    return transition(order, "cancelled", actor, note)


def mark_delivered(order, actor: str) -> dict:
    if order["status"] not in {"processing", "delivery_failed"}:
        raise OrderError("Only a processing order can be marked as delivered.")
    return transition(order, "delivered", actor, "Marked delivered manually")


def refund(order, actor: str, reason: str) -> dict:
    if order["status"] not in {"paid", "processing", "delivered", "delivery_failed"}:
        raise OrderError("This order cannot be refunded.")
    payment = latest_payment(order["id"])
    if payment is not None:
        execute("UPDATE payments SET status = 'refunded' WHERE id = ?", (payment["id"],))
    return transition(order, "refunded", actor, reason)


def expire_stale_orders() -> int:
    rows = query("SELECT * FROM orders WHERE status = 'pending_payment' AND expires_at < ?",
                 (clock.iso(),))
    for row in rows:
        transition(row, "expired", "system", "QR code expired")
    return len(rows)
