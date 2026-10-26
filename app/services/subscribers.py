"""Newsletter subscribers (proposal FR-C11)."""
from __future__ import annotations

import re

from .. import clock
from ..db import execute, query

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


class SubscriberError(Exception):
    pass


def subscribe(email: str) -> str:
    """Return 'created' or 'exists'; raise SubscriberError for invalid input."""
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise SubscriberError("Please enter a valid email address.")
    if query("SELECT 1 FROM subscribers WHERE email = ?", (email,), one=True):
        return "exists"
    execute("INSERT INTO subscribers (email, created_at) VALUES (?,?)", (email, clock.iso()))
    return "created"


def all_emails() -> list:
    return query("SELECT email, created_at FROM subscribers ORDER BY created_at DESC")
