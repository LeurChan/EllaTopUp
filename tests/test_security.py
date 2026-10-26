"""Security headers, order pages and general error handling (proposal section 7)."""
from conftest import csrf_token, post_json, seed_order


def test_security_headers_are_present(client):
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_unknown_page_renders_the_error_template(client):
    response = client.get("/nope")
    assert response.status_code == 404
    assert b"Page not found" in response.data


def test_order_page_shows_the_qr_code(client):
    order = seed_order(client)
    page = client.get(f"/order/{order['order_no']}")
    assert page.status_code == 200
    assert b"<svg" in page.data          # the KHQR code is rendered inline
    assert order["order_no"].encode() in page.data


def test_order_lookup_form_finds_an_order(client):
    order = seed_order(client)
    response = client.post("/lookup",
                           data={"order_no": order["order_no"].lower(),
                                 "csrf_token": csrf_token(client)})
    assert response.status_code == 302
    assert order["order_no"] in response.headers["Location"]


def test_delivery_failure_is_visible_to_the_customer(client, db):
    # Player IDs ending in 9 always fail at the supplier
    order = seed_order(client, player_id="123456789")
    token = csrf_token(client)
    post_json(client, f"/api/orders/{order['order_no']}/simulate-payment", {}, token)
    status = client.get(f"/api/orders/{order['order_no']}").get_json()
    assert status["status"] == "delivery_failed"
    attempts = db.execute("SELECT * FROM supplier_requests WHERE order_id = "
                          "(SELECT id FROM orders WHERE order_no = ?)",
                          (order["order_no"],)).fetchall()
    assert len(attempts) == 3


def test_expired_order_cannot_be_paid(client, db):
    from app import clock

    order = seed_order(client, player_id="123456781")
    db.execute("UPDATE orders SET expires_at = ? WHERE order_no = ?",
               (clock.iso(clock.now() - __import__("datetime").timedelta(minutes=5)),
                order["order_no"]))
    db.commit()

    token = csrf_token(client)
    post_json(client, f"/api/orders/{order['order_no']}/simulate-payment", {}, token)
    status = client.get(f"/api/orders/{order['order_no']}").get_json()
    assert status["status"] == "expired"
