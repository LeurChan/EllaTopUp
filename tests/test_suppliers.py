"""Supplier adapter behaviour and the retry policy (FR-P07, T09)."""
import pytest

from app.services import suppliers


def test_valid_player_gets_a_stable_nickname(app):
    with app.app_context():
        supplier = suppliers.get_supplier()
        first = supplier.lookup_player("mobile-legends-global", "123456789")
        second = supplier.lookup_player("mobile-legends-global", "123456789")
        assert first.nickname == second.nickname
        assert first.nickname != "123456789"


def test_invalid_player_ids_are_rejected(app):
    with app.app_context():
        supplier = suppliers.get_supplier()
        for bad in ("", "12", "abcdef", "000123"):
            with pytest.raises(suppliers.PlayerNotFound):
                supplier.lookup_player("free-fire", bad)


def test_delivery_succeeds_for_a_normal_account(app):
    with app.app_context():
        result = suppliers.get_supplier().deliver(
            {"order_no": "EL1", "player_id": "123456771", "_attempt": 1}
        )
        assert result.ok
        assert result.supplier_ref == "SBX-EL1"


def test_first_attempt_can_fail_and_the_retry_succeeds(app):
    with app.app_context():
        supplier = suppliers.get_supplier()
        first = supplier.deliver({"order_no": "EL2", "player_id": "123456788", "_attempt": 1})
        second = supplier.deliver({"order_no": "EL2", "player_id": "123456788", "_attempt": 2})
        assert not first.ok
        assert second.ok


def test_account_the_supplier_cannot_serve_always_fails(app):
    with app.app_context():
        supplier = suppliers.get_supplier()
        results = [supplier.deliver({"order_no": "EL3", "player_id": "123456789",
                                     "_attempt": attempt}) for attempt in (1, 2, 3)]
        assert all(not result.ok for result in results)
