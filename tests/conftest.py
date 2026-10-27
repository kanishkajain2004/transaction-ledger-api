"""Test setup: point the app at the separate test database before anything connects."""
from app.config import settings

settings.database_url = settings.test_database_url

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    """Build the schema (tables, constraints, trigger) from the real migrations."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", settings.test_database_url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables():
    # TRUNCATE does not fire the row-level immutability trigger, so it can reset the ledger.
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE transactions, accounts"))
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def create_account(client):
    def _create(name: str = "Alice") -> str:
        response = client.post("/accounts", json={"name": name})
        assert response.status_code == 201, response.text
        return response.json()["id"]

    return _create


@pytest.fixture
def post_txn(client):
    def _post(account_id: str, type_: str, amount, reference_id: str, description: str | None = None):
        body = {"type": type_, "amount": amount, "reference_id": reference_id}
        if description is not None:
            body["description"] = description
        return client.post(f"/accounts/{account_id}/transactions", json=body)

    return _post


@pytest.fixture
def balance_of(client):
    def _balance(account_id: str) -> str:
        return client.get(f"/accounts/{account_id}/balance").json()["balance"]

    return _balance
