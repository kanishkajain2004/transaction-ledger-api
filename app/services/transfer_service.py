from sqlalchemy.orm import Session

from app.models import TransactionType
from app.schemas import TransactionOut, TransferCreate, TransferOut
from app.services.account_service import get_account_for_update
from app.services.transaction_service import apply_transaction


def transfer(db: Session, data: TransferCreate) -> TransferOut:
    """Move money between two accounts: debit + credit commit together or not at all.

    Both transaction rows share the transfer's reference_id, so retrying the same
    transfer is rejected as a duplicate instead of moving the money twice.
    """
    try:
        # Lock both rows in a fixed (sorted) order so two opposite transfers (A->B and B->A)
        # running at the same time cannot deadlock each other.
        locked = {
            account_id: get_account_for_update(db, account_id)
            for account_id in sorted([data.from_account_id, data.to_account_id])
        }
        source = locked[data.from_account_id]
        destination = locked[data.to_account_id]

        debit = apply_transaction(
            db,
            source,
            TransactionType.debit,
            data.amount,
            data.description or f"Transfer to {destination.id}",
            data.reference_id,
        )
        credit = apply_transaction(
            db,
            destination,
            TransactionType.credit,
            data.amount,
            data.description or f"Transfer from {source.id}",
            data.reference_id,
        )
        db.commit()
    except Exception:
        # Anything failing after the debit was staged (e.g. duplicate on the destination)
        # rolls back the whole transfer: a partial transfer is never persisted.
        db.rollback()
        raise

    db.refresh(debit)
    db.refresh(credit)
    return TransferOut(
        reference_id=data.reference_id,
        amount=debit.amount,
        debit_transaction=TransactionOut.model_validate(debit),
        credit_transaction=TransactionOut.model_validate(credit),
        from_account_balance=source.balance,
        to_account_balance=destination.balance,
    )
