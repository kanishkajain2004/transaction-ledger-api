import math
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import TransactionType
from app.schemas import Pagination, TransactionCreate, TransactionCreated, TransactionOut, TransactionPage
from app.services import transaction_service

# Transactions are immutable: this router intentionally exposes no PUT/PATCH/DELETE.
router = APIRouter(prefix="/accounts/{account_id}/transactions", tags=["transactions"])


@router.post("", response_model=TransactionCreated, status_code=status.HTTP_201_CREATED)
def add_transaction(account_id: uuid.UUID, payload: TransactionCreate, db: Session = Depends(get_db)):
    transaction, balance = transaction_service.add_transaction(db, account_id, payload)
    return TransactionCreated(transaction=TransactionOut.model_validate(transaction), balance=balance)


@router.get("", response_model=TransactionPage)
def list_transactions(
    account_id: uuid.UUID,
    type: TransactionType | None = Query(None, description="Filter by credit or debit; omit for both"),
    page: int = Query(1, ge=1, description="Page number, starting at 1"),
    limit: int = Query(10, ge=1, le=100, description="Page size (1-100)"),
    db: Session = Depends(get_db),
):
    items, total = transaction_service.list_transactions(db, account_id, type, page, limit)
    return TransactionPage(
        data=[TransactionOut.model_validate(t) for t in items],
        pagination=Pagination(
            page=page,
            limit=limit,
            total_records=total,
            total_pages=math.ceil(total / limit),
        ),
    )
