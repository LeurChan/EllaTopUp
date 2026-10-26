"""Coupon validation and discount calculation (percent, rounded to cents)."""
from __future__ import annotations

from .. import clock
from ..db import query


class CouponError(Exception):
    """Raised with a message that is safe to show to the customer."""


def find(code: str):
    return query("SELECT * FROM coupons WHERE code = ?", ((code or "").strip().upper(),), one=True)


def discount_for(subtotal_cents: int, percent: int) -> int:
    """Half-up rounding so 10% of 1.99 resolves to 0.20, not 0.19."""
    return (subtotal_cents * percent + 50) // 100


def apply(code: str, subtotal_cents: int) -> tuple[dict, int]:
    """Validate a coupon and return (coupon, discount_cents)."""
    coupon = find(code)
    if coupon is None or not coupon["active"]:
        raise CouponError("That coupon code is not valid.")
    expires = clock.parse(coupon["expires_at"])
    if expires is not None and expires < clock.now():
        raise CouponError("This coupon has expired.")
    if coupon["max_uses"] and coupon["used_count"] >= coupon["max_uses"]:
        raise CouponError("This coupon has already been used the maximum number of times.")

    discount = discount_for(subtotal_cents, coupon["discount_percent"])
    return dict(coupon), min(discount, subtotal_cents)


def consume(code: str) -> None:
    from ..db import execute

    execute("UPDATE coupons SET used_count = used_count + 1 WHERE code = ?", ((code or "").upper(),))
