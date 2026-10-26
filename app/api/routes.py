"""JSON API used by the storefront JavaScript (proposal section 6.1)."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from ..security import rate_limit
from ..services import catalog, coupons, orders, payments, subscribers, suppliers

bp = Blueprint("api", __name__)


def ok(**payload):
    payload.setdefault("ok", True)
    return jsonify(payload)


def fail(message: str, code: str = "invalid", status: int = 400):
    return jsonify({"ok": False, "error": message, "code": code}), status


# --------------------------------------------------------------------------- catalog
@bp.get("/games")
def games():
    search = (request.args.get("q") or "").strip()
    rows = []
    for game in catalog.list_games(search=search):
        game["price_from"] = catalog.price_from(game["id"])
        game["product_count"] = len(catalog.list_products(game["id"]))
        rows.append(game)
    return ok(games=rows)


@bp.get("/games/<slug>")
def game(slug: str):
    found = catalog.get_game(slug)
    if not found or not found["active"]:
        return fail("Game not found.", "not_found", 404)
    return ok(game=found, products=catalog.list_products(found["id"]))


# --------------------------------------------------------------------------- checkout inputs
@bp.post("/players/check")
@rate_limit("player")
def check_player():
    data = request.get_json(silent=True) or {}
    slug = (data.get("game") or "").strip()
    player_id = str(data.get("player_id") or "").strip()
    server = str(data.get("server") or "").strip()

    game = catalog.get_game(slug)
    if not game:
        return fail("Please choose a game.")
    if player_id.isdigit() is False or len(player_id) < 5:
        return fail("Player ID must be at least 5 digits.")
    if game["server_type"] == "select" and server not in game["servers"]:
        return fail("Please choose a server.")

    try:
        info = suppliers.get_supplier().lookup_player(slug, player_id, server)
    except suppliers.PlayerNotFound as exc:
        return fail(str(exc), "player_not_found", 404)
    return ok(nickname=info.nickname, player_id=info.player_id)


@bp.post("/coupons/check")
@rate_limit("coupon")
def check_coupon():
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    subtotal = int(data.get("subtotal_cents") or 0)
    if not code:
        return fail("Please enter a coupon code.")
    if subtotal <= 0:
        return fail("Choose a product first.")
    try:
        coupon, discount = coupons.apply(code, subtotal)
    except coupons.CouponError as exc:
        return fail(str(exc), "coupon_invalid", 404)
    return ok(code=coupon["code"], percent=coupon["discount_percent"], discount_cents=discount,
              total_cents=subtotal - discount)


# --------------------------------------------------------------------------- orders
@bp.post("/orders")
@rate_limit("order")
def create_order():
    data = request.get_json(silent=True) or {}
    try:
        order = orders.create_order(
            game_slug=str(data.get("game") or "").strip(),
            product_id=int(data.get("product_id") or 0),
            player_id=str(data.get("player_id") or "").strip(),
            server=str(data.get("server") or "").strip(),
            coupon_code=str(data.get("coupon") or "").strip(),
            player_name=str(data.get("player_name") or "").strip(),
        )
    except (orders.OrderError, ValueError) as exc:
        return fail(str(exc))

    return ok(
        order_no=order["order_no"],
        status=order["status"],
        subtotal_cents=order["subtotal_cents"],
        discount_cents=order["discount_cents"],
        total_cents=order["total_cents"],
        qr_payload=order["qr_payload"],
        expires_at=order["expires_at"],
        status_url=f"/order/{order['order_no']}",
    )


@bp.get("/orders/<order_no>")
def order_status(order_no: str):
    order = orders.get(order_no)
    if not order:
        return fail("Order not found.", "not_found", 404)
    order = orders.settle(order)
    payment = orders.latest_payment(order["id"])
    return ok(
        order_no=order["order_no"],
        status=order["status"],
        total_cents=order["total_cents"],
        item_title=order["item_title"],
        player_name=order["player_name"],
        expires_at=order["expires_at"],
        payment_status=payment["status"] if payment else None,
    )


@bp.post("/orders/<order_no>/simulate-payment")
@rate_limit("order")
def simulate_payment(order_no: str):
    """Sandbox only: pretend the customer paid, so the flow can be demonstrated.

    Disabled the moment PAYMENT_PROVIDER is not "sandbox".
    """
    if current_app.config["PAYMENT_PROVIDER"] != "sandbox":
        return fail("Not available.", "forbidden", 403)

    order = orders.get(order_no)
    if not order:
        return fail("Order not found.", "not_found", 404)

    data = request.get_json(silent=True) or {}
    provider = payments.get_provider()
    amount = data.get("amount_cents")
    provider.simulate_payment(
        order["order_no"],
        amount_cents=int(amount) if amount is not None else None,
        txn_id=data.get("txn_id"),
    )
    settled = orders.settle(order)
    return ok(status=settled["status"])


# --------------------------------------------------------------------------- newsletter
@bp.post("/subscribers")
def subscribe():
    data = request.get_json(silent=True) or {}
    try:
        result = subscribers.subscribe(data.get("email", ""))
    except subscribers.SubscriberError as exc:
        return fail(str(exc))
    message = ("You are already subscribed." if result == "exists"
               else "Thanks, you are subscribed.")
    return ok(state=result, message=message)
