"""The catalog is served from the database (proposal sections 5.1 and 8)."""
from app.services import catalog


def test_catalog_has_ten_entries_for_seven_games(app):
    with app.app_context():
        games = catalog.list_games()
        assert len(games) == 10
        assert len({game["name"] for game in games}) == 7
        mlbb = [game for game in games if game["name"] == "Mobile Legends: Bang Bang"]
        assert len(mlbb) == 4  # four regional entries, per section 1


def test_every_entry_has_products_and_a_starting_price(app):
    with app.app_context():
        for game in catalog.list_games():
            products = catalog.list_products(game["id"])
            assert products, f"{game['slug']} has no products"
            assert catalog.price_from(game["id"]) == min(p["price_cents"] for p in products)


def test_search_matches_short_and_full_names(app):
    with app.app_context():
        assert [g["slug"] for g in catalog.list_games(search="free")] == ["free-fire"]
        assert catalog.list_games(search="zzz") == []


def test_servers_are_decoded_from_json_for_server_select_games(app):
    with app.app_context():
        pubg = catalog.get_game("pubg-mobile")
        assert pubg["server_type"] == "select"
        assert "Asia" in pubg["servers"]


def test_unknown_slug_returns_empty(app):
    with app.app_context():
        assert catalog.get_game("does-not-exist") == {}
