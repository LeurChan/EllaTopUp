"""Admin panel: authentication, dashboard, order handling, catalog and audit."""
from __future__ import annotations

import csv
import io

from flask import (Blueprint, Response, abort, current_app, flash, g, redirect,
                   render_template, request, session, url_for)

from .. import clock
from ..db import execute, query
from ..security import administrator_required, limiter, login_required
from ..services import accounts, audit, catalog, orders, reports, subscribers

bp = Blueprint("admin", __name__)

STATUS_FILTERS = ("pending_payment", "paid", "processing", "delivered", "delivery_failed",
                  "expired", "cancelled", "refunded")
PAGE_SIZE = 15


# --------------------------------------------------------------------------- auth
@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.get("user"):
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        limit, window = current_app.config["RATE_LIMITS"]["login"]
        client = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
        client = client.split(",")[0].strip()
        if not limiter.allow("login", client, limit, window):
            flash("Too many login attempts. Please wait a minute.", "error")
            return render_template("admin/login.html"), 429

        user = accounts.authenticate(username, password)
        if user is None:
            flash("Wrong username or password.", "error")
            return render_template("admin/login.html"), 401

        session.clear()
        session.permanent = True
        session["admin_user_id"] = user["id"]
        audit.record("login", "admin_user", user["id"], "", user["username"])
        if user["must_change_password"]:
            flash("Please choose a new password before continuing.", "info")
            return redirect(url_for("admin.change_password"))
        return redirect(request.args.get("next") or url_for("admin.dashboard"))

    return render_template("admin/login.html")


@bp.post("/logout")
@login_required
def logout():
    audit.record("logout", "admin_user", g.user["id"])
    session.clear()
    return redirect(url_for("admin.login"))


@bp.route("/password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if accounts.authenticate(g.user["username"], current) is None:
            flash("Your current password is not correct.", "error")
        elif new != confirm:
            flash("The two new passwords do not match.", "error")
        else:
            try:
                accounts.set_password(g.user["id"], new)
            except accounts.AccountError as exc:
                flash(str(exc), "error")
            else:
                audit.record("password_change", "admin_user", g.user["id"])
                flash("Password updated.", "success")
                return redirect(url_for("admin.dashboard"))
    return render_template("admin/password.html")


# --------------------------------------------------------------------------- dashboard
@bp.get("/")
@login_required
def dashboard():
    data = reports.dashboard()
    data["failed_orders"] = query(
        "SELECT * FROM orders WHERE status = 'delivery_failed' ORDER BY id DESC LIMIT 5"
    )
    data["awaiting_orders"] = query(
        "SELECT * FROM orders WHERE status = 'pending_payment' ORDER BY id DESC LIMIT 5"
    )
    return render_template("admin/dashboard.html", d=data)


# --------------------------------------------------------------------------- orders
@bp.get("/orders")
@login_required
def order_list():
    status = (request.args.get("status") or "").strip()
    game = (request.args.get("game") or "").strip()
    term = (request.args.get("q") or "").strip()
    page = max(1, int(request.args.get("page") or 1))

    clauses, args = [], []
    if status in STATUS_FILTERS:
        clauses.append("o.status = ?")
        args.append(status)
    if game:
        clauses.append("g.slug = ?")
        args.append(game)
    if term:
        clauses.append("(o.order_no LIKE ? OR o.player_id LIKE ? OR o.player_name LIKE ?)")
        like = f"%{term}%"
        args += [like, like, like]
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    total = query(f"SELECT COUNT(*) AS n FROM orders o JOIN games g ON g.id = o.game_id{where}",
                  tuple(args), one=True)["n"]
    rows = query(
        f"""SELECT o.*, g.name AS game_name, g.slug AS game_slug
            FROM orders o JOIN games g ON g.id = o.game_id{where}
            ORDER BY o.id DESC LIMIT ? OFFSET ?""",
        tuple(args) + (PAGE_SIZE, (page - 1) * PAGE_SIZE),
    )
    return render_template(
        "admin/orders.html",
        orders=rows,
        statuses=STATUS_FILTERS,
        games=catalog.list_games(active_only=False),
        filters={"status": status, "game": game, "q": term, "page": page},
        total=total,
        pages=max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
    )


@bp.get("/orders/<order_no>")
@login_required
def order_detail(order_no: str):
    order = orders.get(order_no)
    if not order:
        abort(404)
    return render_template(
        "admin/order_detail.html",
        order=order,
        payment=orders.latest_payment(order["id"]),
        history=orders.history(order["id"]),
        attempts=query(
            "SELECT * FROM supplier_requests WHERE order_id = ? ORDER BY attempt", (order["id"],)
        ),
        game=catalog.get_game_by_id(order["game_id"]),
    )


def _act(order_no: str, action: str):
    order = orders.get(order_no)
    if not order:
        abort(404)
    old = order["status"]
    try:
        if action == "retry":
            order = orders.retry_delivery(order, g.user["username"])
        elif action == "deliver":
            order = orders.mark_delivered(order, g.user["username"])
        elif action == "cancel":
            order = orders.cancel(order, g.user["username"])
        elif action == "refund":
            reason = (request.form.get("reason") or "").strip()
            if not reason:
                flash("A refund needs a reason.", "error")
                return redirect(url_for("admin.order_detail", order_no=order_no))
            order = orders.refund(order, g.user["username"], reason)
        else:
            abort(404)
    except orders.OrderError as exc:
        flash(str(exc), "error")
    else:
        audit.record(action, "order", order["id"], old, order["status"])
        flash(f"Order {order_no} is now {order['status'].replace('_', ' ')}.", "success")
    return redirect(url_for("admin.order_detail", order_no=order_no))


@bp.post("/orders/<order_no>/retry")
@login_required
def order_retry(order_no: str):
    return _act(order_no, "retry")


@bp.post("/orders/<order_no>/deliver")
@login_required
def order_deliver(order_no: str):
    return _act(order_no, "deliver")


@bp.post("/orders/<order_no>/cancel")
@login_required
def order_cancel(order_no: str):
    return _act(order_no, "cancel")


@bp.post("/orders/<order_no>/refund")
@administrator_required
def order_refund(order_no: str):
    return _act(order_no, "refund")


# --------------------------------------------------------------------------- catalog
@bp.get("/games")
@login_required
def games():
    rows = []
    for game in catalog.list_games(active_only=False):
        products = catalog.list_products(game["id"], active_only=False)
        stats = query(
            """SELECT COUNT(*) AS orders, COALESCE(SUM(total_cents), 0) AS revenue
               FROM orders WHERE game_id = ? AND status IN ('paid','processing','delivered')""",
            (game["id"],), one=True,
        )
        game["products"] = products
        game["orders"] = stats["orders"]
        game["revenue"] = stats["revenue"]
        rows.append(game)
    return render_template("admin/games.html", games=rows)


@bp.post("/games/<int:game_id>/toggle")
@administrator_required
def game_toggle(game_id: int):
    game = catalog.get_game_by_id(game_id)
    if not game:
        abort(404)
    execute("UPDATE games SET active = ? WHERE id = ?", (0 if game["active"] else 1, game_id))
    audit.record("game_toggle", "game", game_id, game["active"], 0 if game["active"] else 1)
    flash(f"{game['name']} is now {'hidden' if game['active'] else 'visible'}.", "success")
    return redirect(url_for("admin.games"))


@bp.get("/coupons")
@login_required
def coupons():
    return render_template("admin/coupons.html",
                           coupons=query("SELECT * FROM coupons ORDER BY code"))


@bp.post("/coupons")
@administrator_required
def coupon_create():
    code = (request.form.get("code") or "").strip().upper()
    percent = int(request.form.get("percent") or 0)
    max_uses = int(request.form.get("max_uses") or 0)
    if not code or not 1 <= percent <= 100:
        flash("A coupon needs a code and a percentage between 1 and 100.", "error")
    else:
        execute(
            "INSERT OR REPLACE INTO coupons (code, discount_percent, max_uses, active) "
            "VALUES (?,?,?,1)", (code, percent, max_uses),
        )
        audit.record("coupon_save", "coupon", code, "", f"{percent}% max={max_uses}")
        flash(f"Coupon {code} saved.", "success")
    return redirect(url_for("admin.coupons"))


@bp.post("/coupons/<code>/toggle")
@administrator_required
def coupon_toggle(code: str):
    row = query("SELECT * FROM coupons WHERE code = ?", (code,), one=True)
    if not row:
        abort(404)
    execute("UPDATE coupons SET active = ? WHERE code = ?", (0 if row["active"] else 1, code))
    audit.record("coupon_toggle", "coupon", code, row["active"], 0 if row["active"] else 1)
    return redirect(url_for("admin.coupons"))


# --------------------------------------------------------------------------- subscribers + audit
@bp.get("/subscribers")
@administrator_required
def subscribers_list():
    return render_template("admin/subscribers.html", subscribers=subscribers.all_emails())


@bp.get("/subscribers.csv")
@administrator_required
def subscribers_csv():
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["email", "created_at"])
    for row in subscribers.all_emails():
        writer.writerow([row["email"], row["created_at"]])
    audit.record("export", "subscribers", "", "", f"{len(subscribers.all_emails())} rows")
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=subscribers.csv"},
    )


@bp.get("/audit")
@administrator_required
def audit_list():
    return render_template("admin/audit.html", entries=audit.recent())


# --------------------------------------------------------------------------- staff accounts
@bp.get("/users")
@administrator_required
def users():
    return render_template("admin/users.html", users=accounts.list_users())


@bp.post("/users")
@administrator_required
def user_create():
    try:
        user_id = accounts.create(request.form.get("username", ""),
                                  request.form.get("password", ""),
                                  request.form.get("role", "operator"))
    except accounts.AccountError as exc:
        flash(str(exc), "error")
    else:
        audit.record("user_create", "admin_user", user_id, "", request.form.get("username"))
        flash("Account created. The new user must change the password at first login.", "success")
    return redirect(url_for("admin.users"))


@bp.post("/users/<int:user_id>/toggle")
@administrator_required
def user_toggle(user_id: int):
    row = query("SELECT * FROM admin_users WHERE id = ?", (user_id,), one=True)
    if not row:
        abort(404)
    accounts.set_active(user_id, not row["active"])
    audit.record("user_toggle", "admin_user", user_id, row["active"], 0 if row["active"] else 1)
    return redirect(url_for("admin.users"))
