"""Admin panel: authentication, roles and the audit trail (proposal section 3, FR-A01/A06)."""
import pytest

from conftest import ADMIN, OPERATOR, csrf_token, login, seed_order


def test_dashboard_requires_a_login(client):
    response = client.get("/admin/")
    assert response.status_code == 302
    assert "/admin/login" in response.headers["Location"]


def test_wrong_password_is_rejected(client):
    response = login(client, {"username": "admin", "password": "wrong-password"})
    assert response.status_code == 401


def test_login_then_dashboard(client):
    assert login(client).status_code == 302
    page = client.get("/admin/")
    assert page.status_code == 200
    assert b"Dashboard" in page.data


def _paid_order(client, db):
    order = seed_order(client)
    db.execute("UPDATE orders SET status = 'paid' WHERE order_no = ?", (order["order_no"],))
    db.execute(
        "UPDATE payments SET status = 'confirmed', provider_txn_id = 'TX-1' "
        "WHERE qr_reference = ?", (order["order_no"],))
    db.commit()
    return order


def test_operator_cannot_refund(client, db):
    order = _paid_order(client, db)
    login(client, OPERATOR)
    response = client.post(
        f"/admin/orders/{order['order_no']}/refund",
        data={"reason": "customer asked", "csrf_token": csrf_token(client)},
    )
    assert response.status_code == 403
    assert db.execute("SELECT status FROM orders WHERE order_no = ?",
                      (order["order_no"],)).fetchone()["status"] == "paid"


def test_administrator_can_refund_and_it_is_audited(client, db):
    order = _paid_order(client, db)
    login(client, ADMIN)
    response = client.post(
        f"/admin/orders/{order['order_no']}/refund",
        data={"reason": "duplicate payment", "csrf_token": csrf_token(client)},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert db.execute("SELECT status FROM orders WHERE order_no = ?",
                      (order["order_no"],)).fetchone()["status"] == "refunded"
    entry = db.execute(
        "SELECT * FROM audit_log WHERE action = 'refund' ORDER BY id DESC"
    ).fetchone()
    assert entry is not None
    assert entry["entity"] == "order"


def test_admin_form_without_csrf_is_refused(client, db):
    order = _paid_order(client, db)
    login(client, ADMIN)
    response = client.post(f"/admin/orders/{order['order_no']}/refund",
                           data={"reason": "no token"})
    assert response.status_code in (302, 400)
    assert db.execute("SELECT status FROM orders WHERE order_no = ?",
                      (order["order_no"],)).fetchone()["status"] == "paid"


def test_refund_requires_a_reason(client, db):
    order = _paid_order(client, db)
    login(client, ADMIN)
    client.post(f"/admin/orders/{order['order_no']}/refund",
                data={"reason": "", "csrf_token": csrf_token(client)})
    assert db.execute("SELECT status FROM orders WHERE order_no = ?",
                      (order["order_no"],)).fetchone()["status"] == "paid"


def test_password_change_is_forced_for_new_accounts(client, db):
    login(client, ADMIN)
    token = csrf_token(client)
    client.post("/admin/users",
                data={"username": "newop", "password": "TempPass123", "role": "operator",
                      "csrf_token": token})
    row = db.execute("SELECT * FROM admin_users WHERE username = 'newop'").fetchone()
    assert row["must_change_password"] == 1

    fresh = client.application.test_client()
    response = fresh.post("/admin/login",
                          data={"username": "newop", "password": "TempPass123",
                                "csrf_token": csrf_token(fresh)})
    assert response.status_code == 302
    assert "/admin/password" in response.headers["Location"]

    blocked = fresh.get("/admin/orders")
    assert "/admin/password" in blocked.headers["Location"]


def test_login_is_rate_limited(client, app):
    from app.security import limiter

    limiter.reset()
    app.config["RATE_LIMITS"] = {**app.config["RATE_LIMITS"], "login": (3, 60)}
    for _ in range(3):
        login(client, {"username": "admin", "password": "nope"})
    response = login(client, {"username": "admin", "password": "nope"})
    assert response.status_code == 429
