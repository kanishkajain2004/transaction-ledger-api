"""Data-integrity guarantees enforced by the database and by row locking."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.database import SessionLocal, engine
from app.errors import AppError
from app.models import TransactionType
from app.schemas import TransactionCreate, TransferCreate
from app.services import transaction_service, transfer_service


def run_concurrently(fn, args_list):
    """Run fn(*args) in parallel threads, each with its own DB session; return per-call outcome."""

    def call(args):
        db = SessionLocal()
        try:
            fn(db, *args)
            return "ok"
        except AppError as exc:
            return exc.code
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=len(args_list)) as pool:
        return list(pool.map(call, args_list))


def credit(amount, ref):
    return TransactionCreate(type=TransactionType.credit, amount=Decimal(amount), reference_id=ref)


def debit(amount, ref):
    return TransactionCreate(type=TransactionType.debit, amount=Decimal(amount), reference_id=ref)


# ---------- Immutability & constraints at the database level ----------

def test_database_blocks_updating_a_transaction(create_account, post_txn):
    account_id = create_account()
    post_txn(account_id, "credit", 10, "r1")

    with pytest.raises(DBAPIError, match="immutable"):
        with engine.begin() as conn:
            conn.execute(text("UPDATE transactions SET amount = 999"))


def test_database_blocks_deleting_a_transaction(create_account, post_txn):
    account_id = create_account()
    post_txn(account_id, "credit", 10, "r1")

    with pytest.raises(DBAPIError, match="immutable"):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM transactions"))


def test_database_rejects_negative_balance(create_account):
    account_id = create_account()

    with pytest.raises(IntegrityError, match="ck_accounts_balance_non_negative"):
        with engine.begin() as conn:
            conn.execute(text("UPDATE accounts SET balance = -1 WHERE id = :id"), {"id": account_id})


def test_database_rejects_duplicate_reference_and_non_positive_amount(create_account, post_txn):
    account_id = create_account()
    post_txn(account_id, "credit", 10, "r1")
    insert = text(
        "INSERT INTO transactions (id, account_id, type, amount, reference_id) "
        "VALUES (:id, :account_id, 'credit', :amount, :ref)"
    )

    with pytest.raises(IntegrityError, match="uq_transactions_account_reference"):
        with engine.begin() as conn:
            conn.execute(insert, {"id": uuid.uuid4(), "account_id": account_id, "amount": 5, "ref": "r1"})
    with pytest.raises(IntegrityError, match="ck_transactions_amount_positive"):
        with engine.begin() as conn:
            conn.execute(insert, {"id": uuid.uuid4(), "account_id": account_id, "amount": 0, "ref": "r2"})


# ---------- Atomicity ----------

def test_failed_insert_does_not_change_balance(create_account, balance_of):
    """If saving the transaction fails at the DB, the already-applied balance change is rolled back."""
    account_id = uuid.UUID(create_account())
    # Bypass API validation to force a DB error (description longer than the column allows).
    bad = TransactionCreate.model_construct(
        type=TransactionType.credit, amount=Decimal("10"), description="x" * 600, reference_id="r1"
    )

    db = SessionLocal()
    try:
        with pytest.raises(DBAPIError):
            transaction_service.add_transaction(db, account_id, bad)
    finally:
        db.close()

    assert balance_of(str(account_id)) == "0.00"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM transactions")).scalar() == 0


# ---------- Concurrency ----------

def test_parallel_debits_never_overdraw(create_account, post_txn, balance_of):
    account_id = create_account()
    post_txn(account_id, "credit", 100, "seed")

    # 20 parallel debits of 10 against a balance of 100: exactly 10 may succeed.
    outcomes = run_concurrently(
        transaction_service.add_transaction,
        [(uuid.UUID(account_id), debit(10, f"d{i}")) for i in range(20)],
    )

    assert outcomes.count("ok") == 10
    assert outcomes.count("INSUFFICIENT_BALANCE") == 10
    assert balance_of(account_id) == "0.00"


def test_parallel_duplicates_create_only_one_transaction(create_account, balance_of):
    account_id = create_account()

    outcomes = run_concurrently(
        transaction_service.add_transaction,
        [(uuid.UUID(account_id), credit(10, "same-ref")) for _ in range(10)],
    )

    assert outcomes.count("ok") == 1
    assert outcomes.count("DUPLICATE_TRANSACTION") == 9
    assert balance_of(account_id) == "10.00"


def test_opposite_parallel_transfers_do_not_deadlock_and_conserve_money(create_account, post_txn, balance_of):
    a, b = create_account("A"), create_account("B")
    post_txn(a, "credit", 100, "seed")
    post_txn(b, "credit", 100, "seed")

    def transfer(from_id, to_id, ref):
        return TransferCreate(
            from_account_id=from_id, to_account_id=to_id, amount=Decimal("1"), reference_id=ref
        )

    jobs = [(transfer(a, b, f"ab{i}"),) for i in range(10)] + [(transfer(b, a, f"ba{i}"),) for i in range(10)]
    outcomes = run_concurrently(transfer_service.transfer, jobs)

    assert outcomes == ["ok"] * 20
    assert (balance_of(a), balance_of(b)) == ("100.00", "100.00")
