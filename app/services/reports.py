"""Dashboard metrics: revenue, averages, 14-day series, top games (proposal FR-A02)."""
from __future__ import annotations

from datetime import timedelta

from .. import clock
from ..db import query

REVENUE_STATUSES = ("paid", "processing", "delivered")


def dashboard(days: int = 14) -> dict:
    placeholders = ",".join("?" * len(REVENUE_STATUSES))
    totals = query(
        f"""SELECT COUNT(*) AS orders,
                   COALESCE(SUM(total_cents), 0) AS revenue,
                   COALESCE(AVG(total_cents), 0) AS average
            FROM orders WHERE status IN ({placeholders})""",
        REVENUE_STATUSES, one=True,
    )
    awaiting = query(
        "SELECT COUNT(*) AS n, COALESCE(SUM(total_cents), 0) AS value FROM orders "
        "WHERE status = 'pending_payment'", one=True,
    )
    today = clock.now().date()
    today_rows = query(
        f"SELECT COUNT(*) AS n FROM orders WHERE status IN ({placeholders}) AND created_at >= ?",
        REVENUE_STATUSES + (f"{today.isoformat()}T00:00:00+00:00",), one=True,
    )
    failed = query("SELECT COUNT(*) AS n FROM orders WHERE status = 'delivery_failed'", one=True)

    series = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        row = query(
            f"""SELECT COALESCE(SUM(total_cents), 0) AS revenue, COUNT(*) AS orders
                FROM orders
                WHERE status IN ({placeholders}) AND created_at >= ? AND created_at < ?""",
            REVENUE_STATUSES + (f"{day.isoformat()}T00:00:00+00:00",
                                f"{(day + timedelta(days=1)).isoformat()}T00:00:00+00:00"),
            one=True,
        )
        series.append({"date": day.isoformat(), "revenue": row["revenue"], "orders": row["orders"]})

    top = query(
        f"""SELECT g.name, g.slug, COUNT(*) AS orders, COALESCE(SUM(o.total_cents), 0) AS revenue
            FROM orders o JOIN games g ON g.id = o.game_id
            WHERE o.status IN ({placeholders})
            GROUP BY g.id ORDER BY revenue DESC LIMIT 5""",
        REVENUE_STATUSES,
    )
    recent = query(
        "SELECT * FROM orders ORDER BY id DESC LIMIT 8"
    )

    return {
        "revenue": totals["revenue"],
        "orders": totals["orders"],
        "average": int(totals["average"] or 0),
        "awaiting_value": awaiting["value"],
        "awaiting_count": awaiting["n"],
        "orders_today": today_rows["n"],
        "failed": failed["n"],
        "series": series,
        "top_games": [dict(r) for r in top],
        "recent": [dict(r) for r in recent],
    }
