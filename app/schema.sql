-- Ella Store schema (proposal section 8.1).
-- Money is stored in integer cents so no floating point rounding can occur.

CREATE TABLE IF NOT EXISTS games (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT    NOT NULL UNIQUE,
    name            TEXT    NOT NULL,
    short_name      TEXT    NOT NULL DEFAULT '',
    logo_text       TEXT    NOT NULL DEFAULT '',
    gradient        TEXT    NOT NULL DEFAULT '',
    accent          TEXT    NOT NULL DEFAULT '',
    unit            TEXT    NOT NULL DEFAULT 'Diamonds',
    server_type     TEXT    NOT NULL DEFAULT 'none'
                    CHECK (server_type IN ('none', 'text', 'select')),
    servers         TEXT    NOT NULL DEFAULT '[]',   -- JSON array when server_type = 'select'
    image_url       TEXT    NOT NULL DEFAULT '',
    sort_order      INTEGER NOT NULL DEFAULT 0,
    active          INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id     INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    title       TEXT    NOT NULL,
    price_cents INTEGER NOT NULL CHECK (price_cents > 0),
    kind        TEXT    NOT NULL DEFAULT 'pack',
    image_url   TEXT    NOT NULL DEFAULT '',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    active      INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS coupons (
    code             TEXT PRIMARY KEY,
    discount_percent INTEGER NOT NULL CHECK (discount_percent BETWEEN 1 AND 100),
    expires_at       TEXT,
    max_uses         INTEGER NOT NULL DEFAULT 0,   -- 0 = unlimited
    used_count       INTEGER NOT NULL DEFAULT 0,
    active           INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no        TEXT    NOT NULL UNIQUE,
    game_id         INTEGER NOT NULL REFERENCES games(id),
    product_id      INTEGER NOT NULL REFERENCES products(id),
    item_title      TEXT    NOT NULL,
    player_id       TEXT    NOT NULL,
    server          TEXT    NOT NULL DEFAULT '',
    player_name     TEXT    NOT NULL DEFAULT '',
    subtotal_cents  INTEGER NOT NULL,
    discount_cents  INTEGER NOT NULL DEFAULT 0,
    total_cents     INTEGER NOT NULL,
    coupon_code     TEXT    REFERENCES coupons(code),
    pay_method      TEXT    NOT NULL DEFAULT 'khqr',
    status          TEXT    NOT NULL DEFAULT 'pending_payment'
                    CHECK (status IN ('pending_payment', 'paid', 'processing', 'delivered',
                                      'delivery_failed', 'expired', 'cancelled', 'refunded')),
    expires_at      TEXT    NOT NULL,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_orders_status  ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);

CREATE TABLE IF NOT EXISTS order_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    old_status  TEXT,
    new_status  TEXT    NOT NULL,
    actor       TEXT    NOT NULL DEFAULT 'system',
    note        TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id        INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    qr_reference    TEXT    NOT NULL,
    qr_payload      TEXT    NOT NULL DEFAULT '',
    amount_cents    INTEGER NOT NULL,
    currency        TEXT    NOT NULL DEFAULT 'USD',
    provider_txn_id TEXT    UNIQUE,
    status          TEXT    NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'confirmed', 'mismatch', 'late', 'refunded')),
    created_at      TEXT    NOT NULL,
    confirmed_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_payments_order ON payments(order_id);

CREATE TABLE IF NOT EXISTS supplier_requests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    attempt      INTEGER NOT NULL,
    result       TEXT    NOT NULL CHECK (result IN ('success', 'failed')),
    supplier_ref TEXT    NOT NULL DEFAULT '',
    message      TEXT    NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS subscribers (
    email      TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_users (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    username             TEXT    NOT NULL UNIQUE,
    password_hash        TEXT    NOT NULL,
    role                 TEXT    NOT NULL CHECK (role IN ('operator', 'administrator')),
    active               INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 1,
    created_at           TEXT    NOT NULL
);

-- Belongs to the payment SIMULATOR only. A real Bakong/ABA integration never
-- touches this table: it asks the bank API instead (see services/payments.py).
CREATE TABLE IF NOT EXISTS simulator_payments (
    reference    TEXT PRIMARY KEY,
    txn_id       TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    paid_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_user_id INTEGER REFERENCES admin_users(id),
    actor         TEXT    NOT NULL DEFAULT '',
    action        TEXT    NOT NULL,
    entity        TEXT    NOT NULL,
    entity_id     TEXT    NOT NULL DEFAULT '',
    old_value     TEXT    NOT NULL DEFAULT '',
    new_value     TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL
);
