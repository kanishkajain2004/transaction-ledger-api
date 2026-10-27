import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AccountNotFoundError
from app.models import Account


def create_account(db: Session, name: str) -> Account:
    # Balance is never taken from the client: it always starts at 0.
    account = Account(name=name)
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def get_account(db: Session, account_id: uuid.UUID) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise AccountNotFoundError(account_id)
    return account


def get_account_for_update(db: Session, account_id: uuid.UUID) -> Account:
    """Load an account and lock its row until the current DB transaction ends.

    Concurrent writers to the same account wait here, so balance checks and
    updates never race each other.
    """
    account = db.scalars(
        select(Account).where(Account.id == account_id).with_for_update()
    ).one_or_none()
    if account is None:
        raise AccountNotFoundError(account_id)
    return account
