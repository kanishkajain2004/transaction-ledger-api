import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import DuplicateTransactionError, InsufficientBalanceError
from app.models import Account, Transaction, TransactionType
from app.schemas import TransactionCreate, TransactionOut
from app.services.account_service import get_account, get_account_for_update

UNIQUE_REFERENCE_CONSTRAINT = "uq_transactions_account_reference"


def _find_by_reference(db: Session, account_id: uuid.UUID, reference_id: str) -> Transaction | None:
    return db.scalars(
        select(Transaction).where(
            Transaction.account_id == account_id,
            Transaction.reference_id == reference_id,
        )
    ).one_or_none()


def _duplicate_error(existing: Transaction) -> DuplicateTransactionError:
    return DuplicateTransactionError(
        f"Transaction with reference_id '{existing.reference_id}' already exists for this account",
        {"transaction": TransactionOut.model_validate(existing).model_dump(mode="json")},
    )


def _is_duplicate_reference(exc: IntegrityError) -> bool:
    return UNIQUE_REFERENCE_CONSTRAINT in str(exc.orig)


def apply_transaction(
    db: Session,
    account: Account,
    type_: TransactionType,
    amount: Decimal,
    description: str | None,
    reference_id: str,
) -> Transaction:
    """Validate and stage one ledger entry on an already-locked account. Does NOT commit.

    The caller owns the DB transaction, so several entries (e.g. a transfer) can be
    committed — or rolled back — together.
    """
    existing = _find_by_reference(db, account.id, reference_id)
    if existing is not None:
        raise _duplicate_error(existing)

    if type_ is TransactionType.debit:
        if account.balance < amount:
            raise InsufficientBalanceError(
                "Insufficient balance for this debit",
                {
                    "account_id": str(account.id),
                    "balance": str(account.balance),
                    "requested_amount": f"{amount:.2f}",
                },
            )
        account.balance -= amount
    else:
        account.balance += amount

    transaction = Transaction(
        account_id=account.id,
        type=type_,
        amount=amount,
        description=description,
        reference_id=reference_id,
    )
    db.add(transaction)
    return transaction


def add_transaction(db: Session, account_id: uuid.UUID, data: TransactionCreate) -> tuple[Transaction, Decimal]:
    """Insert a transaction and update the balance atomically (one DB transaction)."""
    try:
        account = get_account_for_update(db, account_id)
        transaction = apply_transaction(
            db, account, data.type, data.amount, data.description, data.reference_id
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Safety net: the unique constraint caught a duplicate the lock didn't (should be rare).
        if _is_duplicate_reference(exc):
            existing = _find_by_reference(db, account_id, data.reference_id)
            if existing is not None:
                raise _duplicate_error(existing) from exc
        raise
    except Exception:
        # Any failure (rejected debit, duplicate, DB error) leaves balance and ledger untouched.
        db.rollback()
        raise

    db.refresh(transaction)
    return transaction, account.balance


def list_transactions(
    db: Session,
    account_id: uuid.UUID,
    type_: TransactionType | None,
    page: int,
    limit: int,
) -> tuple[list[Transaction], int]:
    """Return one page of an account's transactions (latest first) and the total count."""
    get_account(db, account_id)

    filters = [Transaction.account_id == account_id]
    if type_ is not None:
        filters.append(Transaction.type == type_)

    total = db.scalar(select(func.count()).select_from(Transaction).where(*filters))
    items = db.scalars(
        select(Transaction)
        .where(*filters)
        .order_by(Transaction.created_at.desc(), Transaction.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()
    return list(items), total
