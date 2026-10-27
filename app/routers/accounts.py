import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import AccountCreate, AccountOut, BalanceOut
from app.services import account_service

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)):
    return account_service.create_account(db, payload.name)


@router.get("/{account_id}", response_model=AccountOut)
def get_account(account_id: uuid.UUID, db: Session = Depends(get_db)):
    return account_service.get_account(db, account_id)


@router.get("/{account_id}/balance", response_model=BalanceOut)
def get_balance(account_id: uuid.UUID, db: Session = Depends(get_db)):
    account = account_service.get_account(db, account_id)
    return BalanceOut(account_id=account.id, balance=account.balance)
