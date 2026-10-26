"""Game catalog: entries and their products."""
from __future__ import annotations

import json

from ..db import query


def _to_dict(row) -> dict:
    if row is None:
        return {}
    game = dict(row)
    game["servers"] = json.loads(game.get("servers") or "[]")
    return game


def list_games(active_only: bool = True, search: str = "") -> list[dict]:
    sql = "SELECT * FROM games"
    clauses, args = [], []
    if active_only:
        clauses.append("active = 1")
    if search:
        clauses.append("(name LIKE ? OR short_name LIKE ?)")
        like = f"%{search}%"
        args += [like, like]
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY sort_order, id"
    return [_to_dict(row) for row in query(sql, tuple(args))]


def get_game(slug: str) -> dict:
    return _to_dict(query("SELECT * FROM games WHERE slug = ?", (slug,), one=True))


def get_game_by_id(game_id: int) -> dict:
    return _to_dict(query("SELECT * FROM games WHERE id = ?", (game_id,), one=True))


def list_products(game_id: int, active_only: bool = True) -> list[dict]:
    sql = "SELECT * FROM products WHERE game_id = ?"
    if active_only:
        sql += " AND active = 1"
    sql += " ORDER BY sort_order, id"
    return [dict(row) for row in query(sql, (game_id,))]


def get_product(product_id: int) -> dict:
    row = query("SELECT * FROM products WHERE id = ?", (product_id,), one=True)
    return dict(row) if row else {}


def price_from(game_id: int) -> int:
    row = query(
        "SELECT MIN(price_cents) AS price FROM products WHERE game_id = ? AND active = 1",
        (game_id,),
        one=True,
    )
    return (row["price"] or 0) if row else 0
