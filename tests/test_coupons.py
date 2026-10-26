"""Coupon rules: percentage discount rounded to cents (proposal FR-C07, T03, T04)."""
import pytest

from app.services import coupons


def test_discount_rounds_half_up():
    assert coupons.discount_for(199, 10) == 20      # 19.9 cents -> 20
    assert coupons.discount_for(399, 20) == 80      # 79.8 cents -> 80
    assert coupons.discount_for(99, 10) == 10       # 9.9 -> 10
    assert coupons.discount_for(100, 10) == 10      # exact


def test_valid_coupon_returns_discount(app):
    with app.app_context():
        coupon, discount = coupons.apply("welcome10", 1000)
        assert coupon["code"] == "WELCOME10"
        assert discount == 100


def test_unknown_and_expired_coupons_are_rejected(app):
    with app.app_context():
        with pytest.raises(coupons.CouponError, match="not valid"):
            coupons.apply("NOPE", 1000)
        with pytest.raises(coupons.CouponError, match="expired"):
            coupons.apply("EXPIRED10", 1000)


def test_coupon_stops_after_its_usage_limit(app, db):
    with app.app_context():
        db.execute("UPDATE coupons SET max_uses = 2, used_count = 2 WHERE code = 'ELLA20'")
        db.commit()
        with pytest.raises(coupons.CouponError, match="maximum"):
            coupons.apply("ELLA20", 1000)


def test_discount_never_exceeds_subtotal(app):
    with app.app_context():
        coupon, discount = coupons.apply("ELLA20", 5)
        assert discount <= 5


def test_consume_increments_the_counter(app, db):
    with app.app_context():
        coupons.consume("WELCOME10")
    row = db.execute("SELECT used_count FROM coupons WHERE code = 'WELCOME10'").fetchone()
    assert row["used_count"] == 1
