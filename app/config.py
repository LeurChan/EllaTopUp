"""Configuration read from the environment, with safe development defaults."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader so the project needs no extra dependency."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    DATABASE = os.environ.get("DATABASE") or str(INSTANCE_DIR / "ella.db")

    SESSION_COOKIE_NAME = "ella_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _flag("SESSION_COOKIE_SECURE", "0")
    PERMANENT_SESSION_LIFETIME = 8 * 60 * 60  # proposal section 7.1: 8-hour expiry

    ORDER_TTL_MINUTES = int(os.environ.get("ORDER_TTL_MINUTES", "10"))
    PAYMENT_PROVIDER = os.environ.get("PAYMENT_PROVIDER", "sandbox")
    SUPPLIER_ADAPTER = os.environ.get("SUPPLIER_ADAPTER", "sandbox")

    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "ChangeMe!2026")

    # storefront identity used in the KHQR payload
    STORE_NAME = os.environ.get("STORE_NAME", "ELLA STORE")
    STORE_CITY = os.environ.get("STORE_CITY", "Phnom Penh")
    STORE_BAKONG_ID = os.environ.get("STORE_BAKONG_ID", "ellarstore@aclb")

    DELIVERY_MAX_ATTEMPTS = int(os.environ.get("DELIVERY_MAX_ATTEMPTS", "3"))

    # rate limits: (max requests, window in seconds)
    RATE_LIMITS = {
        "player": (20, 60),
        "coupon": (15, 60),
        "order": (10, 60),
        "login": (5, 60),
    }

    JSON_SORT_KEYS = False


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = True
    PAYMENT_PROVIDER = "sandbox"
    SUPPLIER_ADAPTER = "sandbox"


def load_config(name: str | None = None) -> type[Config]:
    return Config
