"""CSRF protection, session guards, role checks and rate limiting."""
from __future__ import annotations

import secrets
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import abort, current_app, flash, g, jsonify, redirect, request, session, url_for

CSRF_KEY = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def csrf_token() -> str:
    """Return the per-session CSRF token, creating it on first use."""
    if session.get(CSRF_KEY) is None:
        session[CSRF_KEY] = secrets.token_urlsafe(32)
    return session[CSRF_KEY]


def csrf_is_valid() -> bool:
    expected = session.get(CSRF_KEY)
    if not expected:
        return False
    supplied = request.headers.get(CSRF_HEADER) or request.form.get("csrf_token") or ""
    return secrets.compare_digest(expected, supplied)


def wants_json() -> bool:
    return request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json"


def reject_csrf():
    message = "Your session expired. Please reload the page and try again."
    if wants_json():
        return jsonify({"ok": False, "error": message, "code": "csrf"}), 400
    flash(message, "error")
    return redirect(request.referrer or url_for("pages.index"))


# --------------------------------------------------------------------------- access control
def load_user() -> None:
    """Populate g.user from the session on every request."""
    g.user = None
    user_id = session.get("admin_user_id")
    if not user_id:
        return
    from .db import query

    g.user = query(
        "SELECT id, username, role, must_change_password FROM admin_users "
        "WHERE id = ? AND active = 1",
        (user_id,),
        one=True,
    )
    if g.user is None:
        session.clear()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if getattr(g, "user", None) is None:
            if wants_json():
                return jsonify({"ok": False, "error": "authentication required"}), 401
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def role_required(*roles: str):
    """Allow only the listed roles (proposal section 3)."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if g.user["role"] not in roles:
                if wants_json():
                    return jsonify({"ok": False, "error": "forbidden"}), 403
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def administrator_required(view):
    return role_required("administrator")(view)


# --------------------------------------------------------------------------- rate limiting
class RateLimiter:
    """Fixed-window limiter held in memory; good enough for one Gunicorn worker.

    Swap the storage for Redis when the pilot runs several workers.
    """

    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, bucket: str, key: str, limit: int, window: int) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[(bucket, key)]
            while hits and now - hits[0] > window:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def rate_limit(bucket: str):
    """Guard an endpoint using the limits configured for that bucket."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            limit, window = current_app.config["RATE_LIMITS"][bucket]
            client = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
            client = client.split(",")[0].strip()
            if not limiter.allow(bucket, client, limit, window):
                if wants_json():
                    return jsonify({"ok": False, "error": "Too many requests, please slow down."}), 429
                return "Too many requests, please slow down.", 429
            return view(*args, **kwargs)

        return wrapped

    return decorator
