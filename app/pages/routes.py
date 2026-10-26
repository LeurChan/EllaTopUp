"""Customer-facing pages."""
from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import clock
from ..services import catalog, orders, payments, subscribers

bp = Blueprint("pages", __name__)


@bp.get("/")
def index():
    games = []
    for game in catalog.list_games():
        game["price_from"] = catalog.price_from(game["id"])
        games.append(game)
    return render_template("index.html", games=games)


@bp.get("/game/<slug>")
def game(slug: str):
    found = catalog.get_game(slug)
    if not found or not found["active"]:
        abort(404)
    products = catalog.list_products(found["id"])
    return render_template("game.html", game=found, products=products)


@bp.get("/order/<order_no>")
def order_status(order_no: str):
    order = orders.get(order_no)
    if not order:
        abort(404)
    order = orders.settle(order)
    payment = orders.latest_payment(order["id"])
    return render_template(
        "order.html",
        order=order,
        payment=payment,
        qr=payments.qr_svg(payment["qr_payload"]) if payment else "",
        history=orders.history(order["id"]),
        expired=clock.parse(order["expires_at"]) < clock.now(),
        game=catalog.get_game_by_id(order["game_id"]),
    )


@bp.route("/lookup", methods=["GET", "POST"])
def lookup():
    if request.method == "POST":
        order_no = (request.form.get("order_no") or "").strip()
        if order_no and orders.get(order_no):
            return redirect(url_for("pages.order_status", order_no=order_no.upper()))
        flash("We could not find an order with that number.", "error")
    return render_template("lookup.html")


@bp.post("/subscribe")
def subscribe():
    try:
        result = subscribers.subscribe(request.form.get("email", ""))
    except subscribers.SubscriberError as exc:
        flash(str(exc), "error")
    else:
        flash("You are already subscribed." if result == "exists"
              else "Thanks, you are subscribed.", "success")
    return redirect(request.referrer or url_for("pages.index"))
