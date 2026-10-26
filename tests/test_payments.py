"""KHQR payload and payment confirmation rules (proposal FR-P03 to FR-P05)."""
import pytest

from app.services import payments


def test_crc16_matches_the_published_check_value():
    # CRC-16/CCITT-FALSE of "123456789" is 0x29B1
    assert payments.crc16_ccitt("123456789") == "29B1"


def test_payload_is_checksum_valid_and_carries_the_amount():
    payload = payments.build_khqr(
        bakong_id="ellarstore@aclb",
        merchant_name="ELLA STORE",
        city="Phnom Penh",
        amount_cents=199,
        currency="USD",
        bill_number="EL261025ABC123",
    )
    assert payload.startswith("000201")
    assert payments.crc16_ccitt(payload[:-4]) == payload[-4:]
    assert "54041.99" in payload        # tag 54, length 04, 1.99
    assert "5303840" in payload         # tag 53, length 03, 840 = USD
    assert "5802KH" in payload          # country
    assert "EL261025ABC123" in payload  # bill number


def test_unknown_currency_is_refused():
    with pytest.raises(ValueError):
        payments.build_khqr(bakong_id="x", merchant_name="x", city="x",
                            amount_cents=100, currency="EUR")


def test_poll_reports_pending_until_the_simulator_is_paid(app):
    with app.app_context():
        provider = payments.get_provider()
        assert provider.poll("EL-UNKNOWN").status == "pending"


def test_real_provider_is_disabled_until_configured(app):
    with app.app_context():
        provider = payments.get_provider("bakong")
        with pytest.raises(NotImplementedError):
            provider.create({"order_no": "X", "total_cents": 100})
