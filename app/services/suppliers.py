"""Supplier adapters: player-name lookup and top-up delivery.

The sandbox implementation mimics a real supplier's behaviour, including
intermittent failures, so the retry logic can be tested without a contract.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

NICKNAME_ROOTS = [
    "Nova", "Kira", "Rithy", "Sokha", "Dara", "Mony", "Bopha", "Vibol",
    "Chantha", "Sreyneang", "Phalla", "Rachana", "Sovann", "Theara",
]


class PlayerNotFound(Exception):
    """The supplier does not know this Player ID."""


class DeliveryUnavailable(Exception):
    """The supplier could not be reached at all."""


@dataclass(frozen=True)
class PlayerInfo:
    player_id: str
    nickname: str
    server: str = ""


@dataclass(frozen=True)
class DeliveryResult:
    ok: bool
    supplier_ref: str = ""
    message: str = ""


class Supplier:
    name = "abstract"

    def lookup_player(self, game_slug: str, player_id: str, server: str = "") -> PlayerInfo:
        raise NotImplementedError

    def deliver(self, order) -> DeliveryResult:
        raise NotImplementedError


class SandboxSupplier(Supplier):
    """Deterministic fake supplier.

    - any Player ID of 5+ digits resolves to a stable nickname
    - a Player ID ending in "9" always fails delivery, which exercises retries
    - other failures happen on the first attempt for IDs ending in "8"
    """

    name = "sandbox"

    def lookup_player(self, game_slug: str, player_id: str, server: str = "") -> PlayerInfo:
        player_id = (player_id or "").strip()
        if not player_id.isdigit() or len(player_id) < 5:
            raise PlayerNotFound("Player ID must be at least 5 digits.")
        if player_id.startswith("000"):
            raise PlayerNotFound("This Player ID does not exist in the game.")
        digest = hashlib.sha256(f"{game_slug}:{player_id}".encode()).digest()
        root = NICKNAME_ROOTS[digest[0] % len(NICKNAME_ROOTS)]
        return PlayerInfo(player_id, f"{root}{digest[1] % 100:02d}", server)

    def deliver(self, order) -> DeliveryResult:
        player_id = order["player_id"]
        if player_id.endswith("9"):
            return DeliveryResult(False, "", "Supplier rejected the top-up (invalid account).")
        if player_id.endswith("8") and order.get("_attempt", 1) == 1:
            return DeliveryResult(False, "", "Supplier timed out, please retry.")
        return DeliveryResult(True, f"SBX-{order['order_no']}", "Top-up delivered.")


class ApiSupplier(Supplier):
    """Real supplier integration: enabled once an API key is provided (proposal 2.5)."""

    name = "supplier"

    def lookup_player(self, game_slug: str, player_id: str, server: str = "") -> PlayerInfo:
        raise NotImplementedError(
            "No supplier API is configured. Set SUPPLIER_ADAPTER=sandbox to develop offline."
        )

    def deliver(self, order) -> DeliveryResult:  # pragma: no cover
        raise NotImplementedError("No supplier API is configured.")


def get_supplier(name: str | None = None) -> Supplier:
    from flask import current_app

    chosen = name or current_app.config["SUPPLIER_ADAPTER"]
    return {"sandbox": SandboxSupplier, "supplier": ApiSupplier}.get(chosen, SandboxSupplier)()
