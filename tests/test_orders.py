"""Order creation and the status machine (proposal section 4.3)."""
import pytest

from app import clock
from app.services import catalog, orders


def _product(app, slug="mobile-legends-global", title="86 Diamonds"):
    product = next(p for p in catalog.list_products(catalog.get_game(slug)["id"])
                   if p["title"] == title)
    return product["id"]


def test_price_comes_from_the_database_not_the_client(app):
    with app.app_context():
        order = orders.create_order(
            game_slug="mobile-legends-global",
            product_id=_product(app),
            player_id="123456789",
        )
        assert order["subtotal_cents"] == 199
        assert order["discount_cents"] == 0
        assert order["total_cents"] == 199
        assert order["status"] == "pending_payment"


def test_coupon_is_applied_and_counted(app):
    with app.app_context():
        order = orders.create_order(
            game_slug="mobile-legends-global",
            product_id=_product(app),
            player_id="123456789",
            coupon_code="WELCOME10",
        )
        assert order["discount_cents"] == 20
        assert order["total_cents"] == 179
        assert order["coupon_code"] == "WELCOME10"


def test_nickname_is_looked_up_from_the_supplier(app):
    with app.app_context():
        order = orders.create_order(
            game_slug="mobile-legends-global",
            product_id=_product(app),
            player_id="123456789",
        )
        assert order["player_name"]
        assert order["player_name"] != order["player_id"]


def test_product_from_another_game_is_rejected(app):
    with app.app_context():
        with pytest.raises(orders.OrderError, match="does not belong"):
            orders.create_order(
                game_slug="free-fire",
                product_id=_product(app),   # an MLBB product
                player_id="123456789",
            )


def test_server_is_required_for_server_select_games(app):
    with app.app_context():
        with pytest.raises(orders.OrderError, match="server"):
            orders.create_order(
                game_slug="pubg-mobile",
                product_id=_product(app, "pubg-mobile", "60 UC"),
                player_id="123456789",
            )


def test_illegal_transition_is_refused(app):
    with app.app_context():
        order = orders.create_order(
            game_slug="mobile-legends-global",
            product_id=_product(app),
            player_id="123456789",
        )
        with pytest.raises(orders.OrderError, match="Cannot change status"):
            orders.transition(order, "delivered")


def test_unpaid_order_expires_after_its_lifetime(app, db):
    with app.app_context():
        order = orders.create_order(
            game_slug="mobile-legends-global",
            product_id=_product(app),
            player_id="123456789",
        )
        db.execute("UPDATE orders SET expires_at = ? WHERE id = ?",
                   (clock.iso(clock.now() - __import__("datetime").timedelta(minutes=1)),
                    order["id"]))
        db.commit()
        expired = orders.expire_if_stale(orders.get(order["order_no"]))
        assert expired["status"] == "expired"


def test_status_history_is_recorded(app):
    with app.app_context():
        order = orders.create_order(
            game_slug="mobile-legends-global",
            product_id=_product(app),
            player_id="123456789",
        )
        entries = orders.history(order["id"])
        assert [entry["new_status"] for entry in entries] == ["pending_payment"]
        assert entries[0]["actor"] == "customer"


def test_order_numbers_are_unique(app):
    with app.app_context():
        numbers = {orders.new_order_no() for _ in range(50)}
        assert len(numbers) == 50
        assert all(number.startswith("EL") for number in numbers)
