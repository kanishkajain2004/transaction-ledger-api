# Transaction Ledger API

A backend API for a simple transaction ledger: create accounts, post credit/debit transactions,
read balances and paginated transaction history, and transfer money between accounts.

**Stack:** Python 3.11–3.14 · FastAPI · SQLAlchemy 2 · PostgreSQL 16 · Alembic · pytest

---

## Running locally

### Prerequisites

| Tool | Version | Check with |
|---|---|---|
| Python | **3.11, 3.12, 3.13 or 3.14** | `python3 --version` (Windows: `python --version`) |
| Docker | Docker Desktop or Docker Engine, with **Compose v2** | `docker compose version` |

Ports **5433** (PostgreSQL) and **8000** (API) must be free. See [Troubleshooting](#troubleshooting) if they are not.

> **macOS note:** the built-in `/usr/bin/python3` is Python 3.9, which is too old. If
> `python3 --version` shows 3.10 or lower, install a newer Python (e.g. `brew install python@3.12`
> or from [python.org](https://www.python.org/downloads/)) and use that command instead, e.g.
> `python3.12 -m venv .venv` in step 3.

### 1. Get the code
```bash
git clone https://github.com/kanishkajain2004/transaction-ledger-api.git
cd transaction-ledger-api
```
Run every command below from this project folder (the one containing `docker-compose.yml`).

### 2. Start PostgreSQL
Make sure Docker is running, then:
```bash
docker compose up -d --wait
```
This starts PostgreSQL 16 on **localhost:5433** with two databases: `ledger` (used by the app) and
`ledger_test` (used by the automated tests). The command returns once the database is ready.

### 3. Create a virtual environment and install dependencies

macOS / Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Windows (PowerShell):
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

> The virtual environment must be **activated in every new terminal** before running the
> commands below (`source .venv/bin/activate`, or `.venv\Scripts\Activate.ps1` on Windows).
> Your prompt shows `(.venv)` when it is active.

### 4. Create the database schema
```bash
alembic upgrade head
```

### 5. Run the API
```bash
uvicorn app.main:app --reload
```
The API is now running at **http://localhost:8000**:
- **Swagger UI** (interactive API docs, try every endpoint in the browser): http://localhost:8000/docs
- **Test console** (simple page for trying the API by hand): http://localhost:8000/
- Health check: http://localhost:8000/health returns `{"status": "ok"}`

Stop the API with `Ctrl+C`.

### 6. Run the tests
In a second terminal (with the virtual environment activated):
```bash
pytest -v
```
The tests rebuild the separate `ledger_test` database from the migrations and never touch the
`ledger` database. The API does not need to be running for the tests.

### Stopping and resetting
```bash
docker compose down      # stop PostgreSQL (data is kept)
docker compose down -v   # stop PostgreSQL and delete all data
```
After `down -v`, start again from step 2 and re-run `alembic upgrade head`.

### Troubleshooting

| Problem | Fix |
|---|---|
| `Cannot connect to the Docker daemon` | Start Docker Desktop (or the Docker service) and wait until it is running, then retry step 2. |
| `unknown flag: --wait` or `docker-compose: command not found` | You have the old Compose v1. Update Docker Desktop / install the Compose v2 plugin so `docker compose` (with a space) works. |
| Port **8000** already in use | Run the API on another port: `uvicorn app.main:app --reload --port 8001` and open http://localhost:8001/docs. |
| Port **5433** already in use | Change `"5433:5432"` in `docker-compose.yml` (e.g. to `"5434:5432"`) and the port in both URLs in `.env` to match. |
| `pip install` tries to compile packages or fails | Check `python --version` inside the activated venv. It must be 3.11–3.14. Recreate the venv with a supported Python. |
| `alembic: command not found` / `uvicorn: command not found` | The virtual environment is not activated in this terminal. Activate it (step 3). |
| `database "ledger_test" does not exist` | The database volume was created before the test-database init script existed. Recreate it: `docker compose down -v && docker compose up -d --wait`, then `alembic upgrade head`. |
| `relation "accounts" does not exist` | The schema has not been created. Run `alembic upgrade head`. |
| Windows: `running scripts is disabled on this system` | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then activate again. |

---

## API

**Full API documentation, with request and response examples and every error case: [API.md](API.md)**

| Method | Path | Description |
|---|---|---|
| `POST` | `/accounts` | Create an account |
| `GET` | `/accounts/{account_id}` | Get account details |
| `GET` | `/accounts/{account_id}/balance` | Get current balance |
| `POST` | `/accounts/{account_id}/transactions` | Add a credit or debit transaction |
| `GET` | `/accounts/{account_id}/transactions` | Transaction history (filter + pagination, latest first) |
| `POST` | `/transfers` | Transfer money between two accounts (bonus) |
| `GET` | `/health` | Health check |

All errors share one format, `{"error": {"code", "message", "details"}}`, with these status codes:
`400 VALIDATION_ERROR`, `404 ACCOUNT_NOT_FOUND`, `409 DUPLICATE_TRANSACTION`,
`422 INSUFFICIENT_BALANCE`, `405 METHOD_NOT_ALLOWED`, `500 INTERNAL_ERROR`.
See [API.md](API.md#error-format) for details.

---

## Design and data integrity

### Atomicity and consistency
Each write runs inside **one database transaction**. For a transaction request:

1. `SELECT ... FOR UPDATE` locks the account row. Concurrent requests for the same account
   wait their turn.
2. Check for a duplicate `reference_id` (→ 409).
3. For a debit, check the balance (→ 422).
4. Insert the transaction row and update `accounts.balance`.
5. `COMMIT`. On **any** error the code runs `ROLLBACK`, so neither the transaction row nor the
   balance change is saved.

Because the balance is read and updated while the row is locked, parallel requests cannot
overdraw the account or lose an update. The test suite checks this with 20 parallel debits.

**Transfers** lock both accounts **in sorted ID order**, so simultaneous A→B and B→A transfers
cannot deadlock. Both legs are staged in one DB transaction. If anything fails, for example the
credit leg after the debit was already staged, the whole transfer rolls back, so a partial
transfer is never possible.

### Immutability
- The API has no PUT, PATCH or DELETE endpoints for transactions.
- A **PostgreSQL trigger** (`transactions_immutable`) rejects every `UPDATE` or `DELETE` on the
  `transactions` table, so the ledger stays append-only even outside the API.

### Database constraints
These are a second line of defence behind the application checks:

| Constraint | Purpose |
|---|---|
| `CHECK (balance >= 0)` | An account can never go negative |
| `CHECK (amount > 0)` | No zero or negative transactions |
| `transaction_type` enum (`credit`, `debit`) | Only valid types |
| `UNIQUE (account_id, reference_id)` | Duplicate protection, even under race conditions |
| `FOREIGN KEY account_id → accounts.id` (`ON DELETE RESTRICT`) | A transaction always belongs to an existing account |
| `NOT NULL` + non-blank checks on `name` and `reference_id` | Required data is always present |

### Other choices
- **Money** is stored as `NUMERIC(18,2)` and handled as Python `Decimal`, never as float.
- **IDs** are UUIDs generated by the server.
- **Timestamps** are timezone-aware and set by the database with `clock_timestamp()`, so the
  rows a transfer writes inside a single DB transaction still get distinct, ordered times.
- History is ordered by `created_at DESC` (with `id` as a tie-breaker) and backed by an index
  on `(account_id, created_at)`.

---

## Project structure
```
API.md                     # Full API documentation
app/
  main.py                  # FastAPI app: routers + exception handlers
  config.py                # Settings (DATABASE_URL, TEST_DATABASE_URL) from env / .env
  database.py              # Engine, session factory, get_db dependency
  models.py                # SQLAlchemy models: Account, Transaction
  schemas.py               # Pydantic request/response models (validation lives here)
  errors.py                # Error classes + consistent JSON error handlers
  static/index.html        # Optional browser test console served at /
  routers/                 # HTTP layer: accounts, transactions, transfers
  services/                # Business logic: account, transaction, transfer services
alembic/versions/          # Migration: tables, constraints, immutability trigger
tests/                     # pytest suite (API, history, transfers, integrity, concurrency)
docker-compose.yml         # PostgreSQL (+ test DB init script in docker/)
```
