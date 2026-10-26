"""Administrator accounts: creation, authentication, password changes."""
from __future__ import annotations

from werkzeug.security import check_password_hash, generate_password_hash

from .. import clock
from ..db import execute, query

MIN_PASSWORD_LENGTH = 8


class AccountError(Exception):
    pass


def create(username: str, password: str, role: str = "operator") -> int:
    username = (username or "").strip().lower()
    if not username:
        raise AccountError("Username is required.")
    if role not in {"operator", "administrator"}:
        raise AccountError("Unknown role.")
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise AccountError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if query("SELECT 1 FROM admin_users WHERE username = ?", (username,), one=True):
        raise AccountError("That username is already taken.")
    return execute(
        "INSERT INTO admin_users (username, password_hash, role, must_change_password, created_at) "
        "VALUES (?,?,?,?,?)",
        (username, generate_password_hash(password), role, 1, clock.iso()),
    )


def authenticate(username: str, password: str):
    """Return the user row on success, otherwise None. Inactive accounts are rejected."""
    user = query("SELECT * FROM admin_users WHERE username = ?",
                 ((username or "").strip().lower(),), one=True)
    if user is None or not user["active"]:
        return None
    if not check_password_hash(user["password_hash"], password or ""):
        return None
    return user


def set_password(user_id: int, password: str) -> None:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise AccountError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    execute(
        "UPDATE admin_users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
        (generate_password_hash(password), user_id),
    )


def list_users() -> list:
    return query("SELECT id, username, role, active, created_at FROM admin_users ORDER BY id")


def set_active(user_id: int, active: bool) -> None:
    execute("UPDATE admin_users SET active = ? WHERE id = ?", (1 if active else 0, user_id))
