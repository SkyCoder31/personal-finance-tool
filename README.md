# Fenmo Expense Tracker

A minimal, production-quality personal expense tracker built as a take-home
assignment. A FastAPI backend exposes a small REST API; a Streamlit frontend
provides the UI. Money is stored as integer paise and every POST is
idempotent — double-click, refresh, and flaky-network retries are all safe.

---

## Demo

- **Live app**: [_Click Here !!_](https://personal-finance-tool-fenmo.streamlit.app/)

---

## Features

**Core (from the brief)**

- `POST /expenses` — create an expense (amount, category, description, date).
- `GET /expenses?category=&sort=date_desc` — list, filter, and sort expenses.
- Streamlit UI with a form, table, category filter, date sort, and live total.

**Production-quality extras**

- **Idempotent writes.** Every `POST /expenses` carries a client-generated
  `Idempotency-Key`. Replays return `200` with the original row instead of
  creating a duplicate; concurrent replays are resolved at the DB unique
  constraint. Handles double-clicks, refreshes, and retry storms.
- **Exact money.** Amounts are stored as integer paise (`BIGINT`) and
  exchanged as `Decimal` strings. No floating-point drift.
- **Dual-sided validation.** Pydantic on the server (amount > 0,
  ≤ 2 decimals, known category, non-empty description, no future dates) and
  mirrored checks in the UI for fast feedback.
- **Safe HTTP client.** Timeouts + exponential-backoff retries on 5xx. Paired
  with idempotency, retries cannot duplicate writes.
- **Clear UX feedback.** Loading spinners, inline error messages, a success
  toast, and a graceful "can't reach API" state.
- **Useful totals.** A "totals by category" breakdown beneath the list.
- **Tests.** Pytest suite covering idempotency, validation, money
  precision, filtering, and sorting.

---

## Tech stack & why

| Layer         | Choice                  | Why                                                                 |
| ------------- | ----------------------- | ------------------------------------------------------------------- |
| Backend       | **FastAPI**             | Type-driven validation, auto OpenAPI docs, minimal boilerplate.     |
| Persistence   | **SQLite + SQLAlchemy** | Zero-config, ACID, indexed queries. Swap the URL for Postgres later. |
| Frontend      | **Streamlit**           | Lets a thoughtful UI ship in the timebox; free hosting.             |
| Money         | **Integer paise**       | Exact arithmetic; the only safe way to handle currency.             |
| Idempotency   | **UUID + DB UNIQUE**    | Simple, correct, and works under concurrency.                       |

---

## Project structure

```
personal-finance-tool/
├── backend/
│   ├── config.py          # Env-driven settings (one place to change)
│   ├── database.py        # SQLAlchemy engine, session, Expense ORM model
│   ├── models.py          # Pydantic request/response schemas + validators
│   ├── repository.py      # Data access + idempotency + unit conversion
│   └── main.py            # FastAPI routes, error handler, lifespan
├── frontend/
│   ├── api_client.py      # requests.Session with retry/backoff + error type
│   └── app.py             # Streamlit UI (also boots backend on Streamlit Cloud)
├── tests/
│   ├── conftest.py        # Per-test-run temp DB, fresh schema per test
│   └── test_api.py        # Idempotency, validation, filter/sort, precision
├── .streamlit/config.toml # Theme + headless mode
├── start.py               # One-command local dev (backend + frontend)
├── requirements.txt
├── pytest.ini
├── .env.example
└── README.md
```

---

## Getting started (local)

### Prerequisites

- Python 3.10+
- `pip`

### Install

```bash
git clone <repo-url> personal-finance-tool
cd personal-finance-tool
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### Run (single command)

```bash
python start.py
```

This starts the FastAPI backend on `http://127.0.0.1:8000` and the
Streamlit UI on `http://127.0.0.1:8501`.

Interactive API docs: `http://127.0.0.1:8000/docs`

### Run the pieces separately

```bash
# terminal 1 — backend
uvicorn backend.main:app --reload

# terminal 2 — frontend
EMBEDDED_BACKEND=0 streamlit run frontend/app.py
```

### Run the tests

```bash
pytest
```

---

## Deployment — Streamlit Community Cloud

The fastest way to ship this: the Streamlit app starts FastAPI in a daemon
thread on first import, so a single deployment hosts the whole stack.

1. **Push to GitHub.** Any public repo will do.
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in.
3. Click **"New app"** and point it at your repo.
4. Set:
   - **Main file path**: `frontend/app.py`
   - **Python version**: 3.11 (advanced settings)
5. Click **"Deploy"**. Streamlit will install `requirements.txt` and boot
   the app. On first load the embedded FastAPI server also starts.

### Splitting frontend & backend (optional, cleaner)
---

## Design decisions

- **Money as integer paise.** Floats corrupt sums; storing `Decimal` in
  SQLite is fiddly. Storing paise as `BIGINT` and converting at the edges
  is exact, portable, and easy to test.
- **Pydantic-strict parsing.** Rather than silently rounding `1.234` to
  `1.23`, we reject it. For money I would rather make the user confirm
  the intended value than round it for them.
- **Idempotency at the unique-constraint level.** Application-level
  deduplication has race windows; a DB unique index does not. The code
  catches the resulting `IntegrityError` and returns the existing row.
- **The UI rotates the idempotency key after a successful submit only.**
  During a slow POST, repeated clicks reuse the same key (deduped server
  side). A page refresh generates a fresh key — the refresh is a new
  logical attempt by the user.
- **Closed category list.** An open-text field would fragment the data
  set immediately (`"Food"` vs `"food"` vs `"FOOD"`), breaking filters
  and summaries. Easier to loosen later than to clean up dirty data.
- **Embedded backend on Streamlit Cloud.** Single-deployment story for
  the reviewer. The split-service option is documented for real prod.

---

## Trade-offs I made because of the timebox

- **No auth / users.** The brief doesn't ask for it. Multi-user support
  would need user accounts, a `user_id` foreign key on `expenses`, and
  session handling.
- **No edit / delete endpoints.** The brief didn't require them, and
  adding delete well (soft delete, audit trail) is non-trivial.
- **No pagination.** A personal expense list is small; I would add
  `limit`/`cursor` at the first sign of scale.
- **No structured logging / tracing / metrics.** Stdout logs only. In
  real prod I'd plug in `structlog` + OpenTelemetry.
- **CORS is fully open** — fine for a demo, would be pinned to known
  frontend origins in real prod.
- **No rate limiting.** Would sit behind a gateway (nginx, Cloudflare)
  or use `slowapi` in front of the API in real prod.

## Things I intentionally did not do

- Chart dashboards, export to CSV, receipt uploads — nice, not core.
- ORM migrations (Alembic) — not needed when schema fits on one screen.
- Docker — trivial to add; not necessary for either the dev loop or
  Streamlit Cloud.

---

## API reference

### `POST /expenses`

Create an expense.

**Headers**

| Name              | Required | Description                                    |
| ----------------- | -------- | ---------------------------------------------- |
| `Idempotency-Key` | No (strongly recommended) | 8–128-char client-generated key. |

**Body**

```json
{
  "amount": "199.50",
  "category": "Food & Dining",
  "description": "Lunch",
  "date": "2026-04-21"
}
```

**Responses**

- `201 Created` — new record.
- `200 OK` — replay of a request with the same `Idempotency-Key`.
- `422` — validation error (amount ≤ 0, > 2 decimals, future date,
  unknown category, etc.).
- `400` — malformed `Idempotency-Key`.

### `GET /expenses`

Query: `category` (exact match), `sort=date_desc`.

```json
{
  "expenses": [ { "id": "...", "amount": "199.50", ... } ],
  "total": "199.50",
  "count": 1
}
```

---

## License

MIT.
