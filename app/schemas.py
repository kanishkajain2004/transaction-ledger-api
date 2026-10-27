import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models import TransactionType

# Exact money amount: > 0, at most 2 decimal places, fits NUMERIC(18, 2).
PositiveAmount = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=2, examples=["50.00"])]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
ReferenceId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Description = Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=500)]


class RequestModel(BaseModel):
    # Unknown fields (e.g. "balance" when creating an account) are rejected, not silently ignored.
    model_config = ConfigDict(extra="forbid")


# ---------- Accounts ----------

class AccountCreate(RequestModel):
    name: Name


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    balance: Decimal
    created_at: datetime


class BalanceOut(BaseModel):
    account_id: uuid.UUID
    balance: Decimal


# ---------- Transactions ----------

class TransactionCreate(RequestModel):
    type: TransactionType
    amount: PositiveAmount
    description: Description = None
    reference_id: ReferenceId


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    type: TransactionType
    amount: Decimal
    description: str | None
    reference_id: str
    created_at: datetime


class TransactionCreated(BaseModel):
    transaction: TransactionOut
    balance: Decimal


class Pagination(BaseModel):
    page: int
    limit: int
    total_records: int
    total_pages: int


class TransactionPage(BaseModel):
    data: list[TransactionOut]
    pagination: Pagination


# ---------- Transfers ----------

class TransferCreate(RequestModel):
    from_account_id: uuid.UUID
    to_account_id: uuid.UUID
    amount: PositiveAmount
    description: Description = None
    reference_id: ReferenceId

    @model_validator(mode="after")
    def accounts_must_differ(self) -> "TransferCreate":
        if self.from_account_id == self.to_account_id:
            raise ValueError("from_account_id and to_account_id must be different accounts")
        return self


class TransferOut(BaseModel):
    reference_id: str
    amount: Decimal
    debit_transaction: TransactionOut
    credit_transaction: TransactionOut
    from_account_balance: Decimal
    to_account_balance: Decimal
