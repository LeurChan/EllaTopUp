"""KHQR payload generation and the payment provider adapters.

The KHQR string follows the EMVCo merchant-presented QR format used by Bakong:
tag-length-value fields terminated by a CRC-16/CCITT checksum.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass

from flask import current_app

from .. import clock
from ..db import execute, query

CURRENCY_CODES = {"USD": "840", "KHR": "116"}
COUNTRY_CODE = "KH"
MCC = "5999"  # "miscellaneous and specialty retail"


# --------------------------------------------------------------------------- KHQR encoding
def crc16_ccitt(payload: str) -> str:
    """CRC-16/CCITT-FALSE, the checksum required by EMVCo QR codes."""
    crc = 0xFFFF
    for byte in payload.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def tlv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"


def build_khqr(
    *,
    bakong_id: str,
    merchant_name: str,
    city: str,
    amount_cents: int,
    currency: str = "USD",
    bill_number: str = "",
) -> str:
    """Build a dynamic (single-payment) KHQR payload for an exact amount."""
    if currency not in CURRENCY_CODES:
        raise ValueError(f"unsupported currency: {currency}")
    if amount_cents <= 0:
        raise ValueError("amount must be positive")

    merchant = tlv("00", bakong_id) + tlv("01", merchant_name) + tlv("02", city)
    additional = tlv("01", bill_number) if bill_number else ""

    payload = "".join([
        tlv("00", "01"),                       # payload format indicator
        tlv("01", "12"),                       # 12 = dynamic QR (single use)
        tlv("29", merchant),                   # individual merchant account
        tlv("52", MCC),
        tlv("53", CURRENCY_CODES[currency]),
        tlv("54", f"{amount_cents / 100:.2f}"),
        tlv("58", COUNTRY_CODE),
        tlv("62", additional),
    ])
    payload += "6304"                          # CRC tag and length, no value yet
    return payload + crc16_ccitt(payload)


# --------------------------------------------------------------------------- provider contract
@dataclass(frozen=True)
class Charge:
    reference: str
    payload: str
    amount_cents: int
    currency: str


@dataclass(frozen=True)
class PaymentResult:
    status: str                 # pending | paid | failed
    txn_id: str = ""
    amount_cents: int = 0
    currency: str = "USD"


class PaymentProvider:
    """Implementations must be idempotent: poll() may be called many times."""

    name = "abstract"

    def create(self, order) -> Charge:
        raise NotImplementedError

    def poll(self, reference: str) -> PaymentResult:
        raise NotImplementedError


class SandboxProvider(PaymentProvider):
    """Same interface as the bank; marks payments through a local simulator table."""

    name = "sandbox"

    def create(self, order) -> Charge:
        payload = build_khqr(
            bakong_id=current_app.config["STORE_BAKONG_ID"],
            merchant_name=current_app.config["STORE_NAME"],
            city=current_app.config["STORE_CITY"],
            amount_cents=order["total_cents"],
            currency="USD",
            bill_number=order["order_no"],
        )
        return Charge(order["order_no"], payload, order["total_cents"], "USD")

    def poll(self, reference: str) -> PaymentResult:
        row = query("SELECT * FROM simulator_payments WHERE reference = ?", (reference,), one=True)
        if row is None:
            return PaymentResult("pending")
        return PaymentResult("paid", row["txn_id"], row["amount_cents"], "USD")

    # --- test/demo helpers, never used by the storefront flow -----------------
    def simulate_payment(self, reference: str, amount_cents: int | None = None,
                         txn_id: str | None = None) -> None:
        expected = query(
            "SELECT amount_cents FROM payments WHERE qr_reference = ?", (reference,), one=True
        )
        amount = amount_cents if amount_cents is not None else (expected["amount_cents"] if expected else 0)
        execute(
            "INSERT OR REPLACE INTO simulator_payments (reference, txn_id, amount_cents, paid_at) "
            "VALUES (?,?,?,?)",
            (reference, txn_id or f"SBX{secrets.token_hex(4).upper()}", amount, clock.iso()),
        )


class BakongProvider(PaymentProvider):
    """Real integration: blocked until the merchant credentials arrive (proposal 2.5)."""

    name = "bakong"

    def create(self, order) -> Charge:  # pragma: no cover - needs credentials
        raise NotImplementedError(
            "Bakong integration is not configured. Set PAYMENT_PROVIDER=sandbox for now."
        )

    def poll(self, reference: str) -> PaymentResult:  # pragma: no cover
        raise NotImplementedError("Bakong integration is not configured.")


def get_provider(name: str | None = None) -> PaymentProvider:
    chosen = name or current_app.config["PAYMENT_PROVIDER"]
    return {"sandbox": SandboxProvider, "bakong": BakongProvider}.get(chosen, SandboxProvider)()


def qr_svg(payload: str, scale: int = 4) -> str:
    """Render a KHQR payload as inline SVG — no third-party image service, no JS library."""
    if not payload:
        return ""
    import segno

    return segno.make(payload, error="m").svg_inline(scale=scale, dark="#0f172a", light="#ffffff")
