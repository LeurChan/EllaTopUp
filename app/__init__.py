"""Application factory."""
from __future__ import annotations

from pathlib import Path

import click
from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for

from . import clock, db
from .config import INSTANCE_DIR, Config

__all__ = ["create_app"]


def create_app(config_overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

    app.teardown_appcontext(db.close_db)

    _register_security(app)
    _register_blueprints(app)
    _register_cli(app)
    _register_errors(app)
    _register_template_helpers(app)
    return app


# --------------------------------------------------------------------------- hooks
def _register_security(app: Flask) -> None:
    from .security import UNSAFE_METHODS, csrf_is_valid, load_user, reject_csrf

    @app.before_request
    def _guard():
        load_user()
        if request.method in UNSAFE_METHODS and not csrf_is_valid():
            return reject_csrf()
        if g.user is not None and g.user["must_change_password"]:
            allowed = {"admin.change_password", "admin.logout", "static"}
            if request.endpoint not in allowed:
                return redirect(url_for("admin.change_password"))
        return None

    @app.after_request
    def _headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; form-action 'self'; frame-ancestors 'none'",
        )
        if request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


def _register_blueprints(app: Flask) -> None:
    from .admin.routes import bp as admin_bp
    from .api.routes import bp as api_bp
    from .pages.routes import bp as pages_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/admin")


def _register_errors(app: Flask) -> None:
    def _payload(message: str, code: str, status: int):
        if request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
            return jsonify({"ok": False, "error": message, "code": code}), status
        return render_template("error.html", message=message, status=status), status

    @app.errorhandler(400)
    def _bad_request(_error):
        return _payload("Bad request.", "bad_request", 400)

    @app.errorhandler(403)
    def _forbidden(_error):
        return _payload("You do not have permission to do that.", "forbidden", 403)

    @app.errorhandler(404)
    def _not_found(_error):
        return _payload("Page not found.", "not_found", 404)

    @app.errorhandler(405)
    def _not_allowed(_error):
        return _payload("Method not allowed.", "method_not_allowed", 405)

    @app.errorhandler(429)
    def _too_many(_error):
        return _payload("Too many requests, please slow down.", "rate_limited", 429)

    @app.errorhandler(500)
    def _server_error(_error):
        return _payload("Something went wrong on our side.", "server_error", 500)


def _register_template_helpers(app: Flask) -> None:
    from .security import csrf_token

    @app.template_filter("usd")
    def _usd(cents) -> str:
        return f"${(int(cents or 0) / 100):,.2f}"

    @app.template_filter("localtime")
    def _localtime(value) -> str:
        return clock.local_str(value)

    @app.context_processor
    def _inject():
        return {"csrf_token": csrf_token, "current_user": g.get("user", None)}


def _register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    @click.option("--seed/--no-seed", default=True, help="Insert the catalog, coupons and admin.")
    def init_db(seed: bool) -> None:
        """Create the schema, then optionally seed it."""
        conn = db.connect(app.config["DATABASE"])
        db.create_schema(conn)
        if seed:
            db.seed(conn, app.config["ADMIN_USERNAME"], app.config["ADMIN_PASSWORD"])
        conn.close()
        click.echo(f"Database ready at {app.config['DATABASE']}")

    @app.cli.command("expire-orders")
    def expire_orders() -> None:
        """Mark unpaid orders past their QR lifetime as expired (run from cron)."""
        with app.app_context():
            from .services import orders

            total = orders.expire_stale_orders()
        click.echo(f"Expired {total} order(s).")
