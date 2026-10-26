"""End-to-end behaviour through the JSON API: T01, T02, T05, T06, T07, T11."""
from conftest import csrf_token, post_json, seed_order


def test_order_requires_a_csrf_token(client):
    response = client.post("/api/orders", json={"game": "free-fire", "product_id": 1})
    assert response.status_code == 400
    assert response.get_json()["code"] == "csrf"


def test_unknown_product_is_rejected_without_saving_an_order(client, db):
    token = csrf_token(client)
    response = post_json(client, "/api/orders",
                         {"game": "free-fire", "product_id": 999999,
                          "player_id": "123456789"}, token)
    assert response.status_code == 400
    assert "product" in response.get_json()["error"].lower()
    assert db.execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"] == 0


def test_client_cannot_choose_the_price(client):
    payload = seed_order(client)
    assert payload["total_cents"] == 199


def test_full_sandbox_flow_reaches_delivered(client):
    order = seed_order(client)
    token = csrf_token(client)

    paid = post_json(client, f"/api/orders/{order['order_no']}/simulate-payment", {}, token)
    assert paid.status_code == 200
    assert paid.get_json()["status"] == "delivered"

    status = client.get(f"/api/orders/{order['order_no']}").get_json()
    assert status["status"] == "delivered"
    assert status["payment_status"] == "confirmed"


def test_wrong_amount_is_recorded_as_a_mismatch(client, db):
    order = seed_order(client)
    token = csrf_token(client)
    post_json(client, f"/api/orders/{order['order_no']}/simulate-payment",
              {"amount_cents": 100}, token)

    row = db.execute(
        "SELECT status FROM payments WHERE qr_reference = ?", (order["order_no"],)
    ).fetchone()
    assert row["status"] == "mismatch"

    status = client.get(f"/api/orders/{order['order_no']}").get_json()
    assert status["status"] == "pending_payment"


def test_same_transaction_id_cannot_pay_two_orders(client, db):
    first = seed_order(client, player_id="123456781")
    second = seed_order(client, player_id="123456782")
    token = csrf_token(client)

    post_json(client, f"/api/orders/{first['order_no']}/simulate-payment",
              {"txn_id": "ABA-TXN-1"}, token)
    post_json(client, f"/api/orders/{second['order_no']}/simulate-payment",
              {"txn_id": "ABA-TXN-1"}, token)

    statuses = dict(db.execute(
        "SELECT o.order_no, p.status FROM orders o JOIN payments p ON p.order_id = o.id"
    ).fetchall())
    assert statuses[first["order_no"]] == "confirmed"
    assert statuses[second["order_no"]] == "mismatch"


def test_player_check_returns_the_nickname(client):
    token = csrf_token(client)
    response = post_json(client, "/api/players/check",
                         {"game": "free-fire", "player_id": "987654321"}, token)
    assert response.status_code == 200
    assert response.get_json()["nickname"]


def test_player_check_rejects_short_ids(client):
    token = csrf_token(client)
    response = post_json(client, "/api/players/check",
                         {"game": "free-fire", "player_id": "12"}, token)
    assert response.status_code == 400


def test_coupon_endpoint_reports_the_discount(client):
    token = csrf_token(client)
    response = post_json(client, "/api/coupons/check",
                         {"code": "ELLA20", "subtotal_cents": 499}, token)
    body = response.get_json()
    assert body["discount_cents"] == 100
    assert body["total_cents"] == 399


def test_unknown_order_returns_404(client):
    assert client.get("/api/orders/EL000000NOPE").status_code == 404


def test_newsletter_accepts_and_deduplicates(client, db):
    token = csrf_token(client)
    first = post_json(client, "/api/subscribers", {"email": "kid@example.com"}, token)
    second = post_json(client, "/api/subscribers", {"email": "kid@example.com"}, token)
    assert first.get_json()["state"] == "created"
    assert second.get_json()["state"] == "exists"
    assert db.execute("SELECT COUNT(*) AS n FROM subscribers").fetchone()["n"] == 1
