# Ella Store — Online Game Top-Up System

Graduation project (Royal University of Phnom Penh style proposal), built by
Chhim Sophal, Seng Sodevit and Chan Punleur.

A Flask + SQLite web application that replaces manual game top-up selling over
chat: the customer verifies a Player ID, pays with an ABA KHQR code, and the
top-up is delivered through a supplier API — no manual work by the seller.

## Status

This repository contains the **core vertical slice**:

- game catalog and products served from the database
- top-up flow: Player ID check → product → coupon → order → KHQR → delivery
- payment and supplier **adapters** with sandbox simulators (real providers plug in)
- order status page and order lookup
- admin panel: login, roles, dashboard, order handling, catalog, coupons, audit log
- automated tests for pricing, coupons, status transitions, KHQR payload and access control

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS
pip install -r requirements.txt

copy .env.example .env          # then edit SECRET_KEY
python -m flask --app run init-db --seed
python run.py                   # http://127.0.0.1:5000
```

The first administrator is created by `init-db` from `ADMIN_USERNAME` /
`ADMIN_PASSWORD` in `.env`, and must change the password at first login.

## Tests

```bash
pytest
```

## Layout

```
app/
  __init__.py        application factory, security headers, error handlers
  db.py              sqlite connection, schema, seeding
  schema.sql         tables from proposal section 8
  security.py        CSRF, login/role guards, rate limiting
  services/          business logic, no HTTP
    catalog.py       games and products
    coupons.py       validation and discount
    orders.py        server-side pricing, status machine, delivery orchestration
    payments.py      KHQR payload + payment providers (sandbox, bakong stub)
    suppliers.py     player lookup and delivery adapters (sandbox, real stub)
    reports.py       dashboard metrics
    accounts.py      administrator accounts
    audit.py         audit trail
  api/               JSON endpoints under /api
  pages/             HTML pages rendered by Jinja2
  admin/             admin panel under /admin
  templates/         Jinja2 templates
  static/            CSS and ES modules
tests/               pytest suite
```

## Security notes

- all money is calculated on the server from the database; the client total is ignored
- passwords hashed with Werkzeug (scrypt), 8-hour sessions, `HttpOnly` + `SameSite=Lax`
- CSRF token required on every state-changing request
- rate limits on player check, coupon and order endpoints
- secrets come from the environment, never from the repository

## Payments and delivery

Both are behind interfaces (`app/services/payments.py`, `app/services/suppliers.py`).
The sandbox implementations behave like the real thing for tests and demos; the
production classes raise `NotImplementedError` until credentials arrive, which is
the limitation stated in the proposal (section 2.5).
