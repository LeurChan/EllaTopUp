"""Audit trail for every change made in the admin panel (proposal FR-A09)."""
from __future__ import annotations

from flask import g

from .. import clock
from ..db import execute


def record(action: str, entity: str, entity_id: str = "", old: str = "", new: str = "") -> None:
    user = getattr(g, "user", None)
    execute(
        "INSERT INTO audit_log (admin_user_id, actor, action, entity, entity_id, old_value, "
        "new_value, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (user["id"] if user else None, user["username"] if user else "system",
         action, entity, str(entity_id), str(old), str(new), clock.iso()),
    )


def recent(limit: int = 200) -> list:
    from ..db import query

    return query("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
