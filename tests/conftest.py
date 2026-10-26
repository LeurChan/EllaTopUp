"""Shared pytest fixtures: a seeded application bound to a temporary database."""
from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app import db as db_module

ADMIN = {"username": "admin", "password": "AdminPass123"}
OPERATOR = {"username": "operator", "password": "OperatorPass123"}

TMP_ROOT = Path(__file__).parent / ".tmp"


@pytest.fixture
def app():
    # A plain directory under tests/ rather than pytest's tmp_path: keeps the
    # suite runnable in restricted environments where 0700 temp dirs are blocked.
    workdir = TMP_ROOT / uuid.uuid4().hex
    workdir.mkdir(parents=True)
    database = workdir / "test.db"
    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE": str(database),
            "ADMIN_USERNAME": ADMIN["username"],
            "ADMIN_PASSWORD": ADMIN["password"],
            "PAYMENT_PROVIDER": "sandbox",
            "SUPPLIER_ADAPTER": "sandbox",
            "RATE_LIMITS": {name: (1000, 60) for name in
                            ("player", "coupon", "order", "login")},
        }
    )

    with application.app_context():
        conn = db_module.connect(application.config["DATABASE"])
        db_module.create_schema(conn)
        db_module.seed(conn, ADMIN["username"], ADMIN["password"])
        conn.execute("UPDATE admin_users SET must_change_password = 0")
        conn.execute(
            "INSERT INTO admin_users (username, password_hash, role, must_change_password, "
            "created_at) VALUES (?,?,?,?,?)",
            (OPERATOR["username"], generate_password_hash(OPERATOR["password"]), "operator", 0,
             "2026-01-01T00:00:00+00:00"),
        )
        conn.commit()
        conn.close()

    from app.security import limiter

    limiter.reset()
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    """Direct read access to the test database, independent of request context."""
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


# --------------------------------------------------------------------------- helpers
def csrf_token(client) -> str:
    """Fetch a page so the session gets a token, then read it back."""
    client.get("/")
    with client.session_transaction() as session:
        return session["csrf_token"]


def post_json(client, path, payload, token=None):
    headers = {"X-CSRF-Token": token or csrf_token(client)}
    return client.post(path, json=payload, headers=headers)


def login(client, credentials=None):
    credentials = credentials or ADMIN
    token = csrf_token(client)
    return client.post(
        "/admin/login",
        data={**credentials, "csrf_token": token},
        follow_redirects=False,
    )


def seed_order(client, *, player_id="123456771", coupon="", product_title="86 Diamonds",
               game="mobile-legends-global", token=None):
    """Create an order through the API and return the JSON payload.

    The default Player ID ends in 1 so the sandbox supplier delivers successfully;
    IDs ending in 8 fail once (retry case) and IDs ending in 9 always fail.
    """
    token = token or csrf_token(client)
    game_data = client.get(f"/api/games/{game}").get_json()
    product = next(p for p in game_data["products"] if p["title"] == product_title)
    response = post_json(
        client,
        "/api/orders",
        {"game": game, "product_id": product["id"], "player_id": player_id, "coupon": coupon},
        token,
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()
