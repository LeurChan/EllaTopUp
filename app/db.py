"""SQLite access: one connection per request, schema creation and seed data."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import current_app, g

from . import clock


def connect(path: str | Path) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc: BaseException | None = None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def query(sql: str, args: tuple = (), one: bool = False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


def execute(sql: str, args: tuple = ()) -> int:
    conn = get_db()
    cur = conn.execute(sql, args)
    conn.commit()
    return cur.lastrowid


# --------------------------------------------------------------------------- schema + seed
SCHEMA = Path(__file__).with_name("schema.sql")

GAMES = [
    # slug, name, short, logo, gradient, accent, unit, server_type, servers, order
    ("mobile-legends-global", "Mobile Legends: Bang Bang", "MLBB Global", "ML",
     "linear-gradient(135deg,#1e3a8a,#0ea5e9)", "#38bdf8", "Diamonds", "none", [], 1),
    ("mobile-legends-my", "Mobile Legends: Bang Bang", "MLBB Malaysia", "ML",
     "linear-gradient(135deg,#7c2d12,#f59e0b)", "#fbbf24", "Diamonds", "none", [], 2),
    ("mobile-legends-ph", "Mobile Legends: Bang Bang", "MLBB Philippines", "ML",
     "linear-gradient(135deg,#7f1d1d,#ef4444)", "#f87171", "Diamonds", "none", [], 3),
    ("mobile-legends-sg", "Mobile Legends: Bang Bang", "MLBB Singapore", "ML",
     "linear-gradient(135deg,#134e4a,#14b8a6)", "#2dd4bf", "Diamonds", "none", [], 4),
    ("free-fire", "Free Fire", "Free Fire", "FF",
     "linear-gradient(135deg,#431407,#f97316)", "#fb923c", "Diamonds", "none", [], 5),
    ("pubg-mobile", "PUBG Mobile", "PUBG Mobile", "PM",
     "linear-gradient(135deg,#0f172a,#64748b)", "#94a3b8", "UC", "select",
     ["Asia", "Europe", "North America", "South America", "KRJP"], 6),
    ("genshin-impact", "Genshin Impact", "Genshin", "GI",
     "linear-gradient(135deg,#164e63,#22d3ee)", "#67e8f9", "Crystals", "select",
     ["Asia", "America", "Europe", "TW/HK/MO"], 7),
    ("honkai-star-rail", "Honkai: Star Rail", "Star Rail", "HSR",
     "linear-gradient(135deg,#3b0764,#a855f7)", "#c084fc", "Oneiric Shards", "select",
     ["Asia", "America", "Europe", "TW/HK/MO"], 8),
    ("valorant", "Valorant", "Valorant", "VP",
     "linear-gradient(135deg,#450a0a,#f43f5e)", "#fb7185", "VP", "none", [], 9),
    ("roblox", "Roblox", "Roblox", "RB",
     "linear-gradient(135deg,#1f2937,#e5e7eb)", "#e5e7eb", "Robux", "none", [], 10),
]

PRODUCTS = {
    "mobile-legends-global": [("86 Diamonds", 199), ("172 Diamonds", 399),
                              ("257 Diamonds", 599), ("Weekly Diamond Pass", 149)],
    "mobile-legends-my": [("86 Diamonds", 199), ("172 Diamonds", 399), ("257 Diamonds", 599)],
    "mobile-legends-ph": [("86 Diamonds", 199), ("172 Diamonds", 399), ("257 Diamonds", 599)],
    "mobile-legends-sg": [("86 Diamonds", 199), ("172 Diamonds", 399), ("257 Diamonds", 599)],
    "free-fire": [("100 Diamonds", 99), ("310 Diamonds", 299),
                  ("520 Diamonds", 499), ("Weekly Membership", 199)],
    "pubg-mobile": [("60 UC", 99), ("325 UC", 499), ("660 UC", 999)],
    "genshin-impact": [("60 Genesis Crystals", 99), ("330 Genesis Crystals", 499),
                       ("1090 Genesis Crystals", 1499)],
    "honkai-star-rail": [("60 Oneiric Shards", 99), ("330 Oneiric Shards", 499),
                         ("1090 Oneiric Shards", 1499)],
    "valorant": [("475 VP", 499), ("1000 VP", 999), ("2050 VP", 1999)],
    "roblox": [("400 Robux", 499), ("800 Robux", 999), ("1700 Robux", 1999)],
}

COUPONS = [
    ("WELCOME10", 10, 0, None),   # code, percent, max_uses, expires_at
    ("ELLA20", 20, 50, None),
    ("EXPIRED10", 10, 0, "2026-01-01T00:00:00+00:00"),
]


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.commit()


def seed(conn: sqlite3.Connection, admin_username: str, admin_password: str) -> None:
    """Insert the catalog, coupons and the first administrator (idempotent)."""
    from werkzeug.security import generate_password_hash

    for row in GAMES:
        slug, name, short, logo, gradient, accent, unit, server_type, servers, order = row
        conn.execute(
            """INSERT OR IGNORE INTO games
               (slug, name, short_name, logo_text, gradient, accent, unit, server_type,
                servers, sort_order)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (slug, name, short, logo, gradient, accent, unit, server_type,
             __import__("json").dumps(servers), order),
        )

    for slug, items in PRODUCTS.items():
        game = conn.execute("SELECT id FROM games WHERE slug = ?", (slug,)).fetchone()
        if not game:
            continue
        for index, (title, price) in enumerate(items, start=1):
            exists = conn.execute(
                "SELECT 1 FROM products WHERE game_id = ? AND title = ?", (game["id"], title)
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO products (game_id, title, price_cents, sort_order) VALUES (?,?,?,?)",
                    (game["id"], title, price, index),
                )

    for code, percent, max_uses, expires in COUPONS:
        conn.execute(
            "INSERT OR IGNORE INTO coupons (code, discount_percent, max_uses, expires_at) "
            "VALUES (?,?,?,?)",
            (code, percent, max_uses, expires),
        )

    exists = conn.execute("SELECT 1 FROM admin_users WHERE username = ?", (admin_username,)).fetchone()
    if not exists:
        conn.execute(
            "INSERT INTO admin_users (username, password_hash, role, must_change_password, created_at) "
            "VALUES (?,?,?,?,?)",
            (admin_username, generate_password_hash(admin_password), "administrator", 1,
             clock.iso()),
        )
    conn.commit()
