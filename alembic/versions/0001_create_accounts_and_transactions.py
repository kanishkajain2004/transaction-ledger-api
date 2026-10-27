"""create accounts and transactions

Revision ID: 0001
Revises:
Create Date: 2026-10-28
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.CheckConstraint("balance >= 0", name="ck_accounts_balance_non_negative"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_accounts_name_not_blank"),
    )

    transaction_type = postgresql.ENUM("credit", "debit", name="transaction_type")

    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("type", transaction_type, nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("reference_id", sa.String(100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.UniqueConstraint("account_id", "reference_id", name="uq_transactions_account_reference"),
        sa.CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
        sa.CheckConstraint("length(trim(reference_id)) > 0", name="ck_transactions_reference_not_blank"),
    )
    op.create_index("ix_transactions_account_created", "transactions", ["account_id", "created_at"])

    # Transactions are an append-only ledger: block UPDATE and DELETE at the database level,
    # so they stay immutable even if someone bypasses the API.
    op.execute(
        """
        CREATE FUNCTION prevent_transaction_modification() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'transactions are immutable: % is not allowed', TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER transactions_immutable
        BEFORE UPDATE OR DELETE ON transactions
        FOR EACH ROW EXECUTE FUNCTION prevent_transaction_modification();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS transactions_immutable ON transactions")
    op.execute("DROP FUNCTION IF EXISTS prevent_transaction_modification()")
    op.drop_index("ix_transactions_account_created", table_name="transactions")
    op.drop_table("transactions")
    op.execute("DROP TYPE IF EXISTS transaction_type")
    op.drop_table("accounts")
