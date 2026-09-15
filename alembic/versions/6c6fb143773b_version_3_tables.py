"""version 3 tables

Revision ID: 6c6fb143773b
Revises: f197591ad7ce
Create Date: 2026-09-14 21:31:53.452841

"""

from typing import Sequence, Union
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6c6fb143773b"
down_revision: Union[str, None] = "f197591ad7ce"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "game_time",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("day", sa.String(length=20), nullable=True),
        sa.Column("hour", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "id = 1",
            name="ck_game_time_single_row",
        ),
        sa.CheckConstraint(
            "hour IS NULL OR (hour >= 0 AND hour <= 23)",
            name="ck_game_time_valid_hour",
        ),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO game_time (id, day, hour)
            VALUES (1, NULL, NULL)
            """
        )
    )
    op.create_table(
        "inventory_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "transaction_type",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column("cart_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("game_day", sa.String(length=20), nullable=True),
        sa.Column("game_hour", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["cart_id"],
            ["carts.id"],
            name="fk_inventory_transactions_cart_id",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "game_hour IS NULL OR (game_hour >= 0 AND game_hour <= 23)",
            name="ck_inventory_transactions_valid_game_hour",
        ),
    )

    op.create_index(
        "ix_inventory_transactions_created_at",
        "inventory_transactions",
        ["created_at"],
    )

    op.create_table(
        "processed_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "operation_type",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "request_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column("transaction_id", sa.Integer(), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["inventory_transactions.id"],
            name="fk_processed_requests_transaction_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "operation_type",
            "request_id",
            name="uq_processed_requests_operation_request",
        ),
        sa.CheckConstraint(
            """
            response_status IS NULL
            OR (response_status >= 100 AND response_status <= 599)
            """,
            name="ck_processed_requests_valid_status",
        ),
    )

    op.create_table(
        "gold_ledger_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("transaction_id", sa.Integer(), nullable=False),
        sa.Column("change", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["inventory_transactions.id"],
            name="fk_gold_ledger_entries_transaction_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "transaction_id",
            name="uq_gold_ledger_entries_transaction",
        ),
        sa.CheckConstraint(
            "change <> 0",
            name="ck_gold_ledger_entries_nonzero_change",
        ),
    )

    op.create_table(
        "ingredient_ledger_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("transaction_id", sa.Integer(), nullable=False),
        sa.Column(
            "ingredient_type",
            sa.String(length=10),
            nullable=False,
        ),
        sa.Column("change", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["inventory_transactions.id"],
            name="fk_ingredient_ledger_entries_transaction_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "transaction_id",
            "ingredient_type",
            name="uq_ingredient_ledger_transaction_type",
        ),
        sa.CheckConstraint(
            "ingredient_type IN ('red', 'green', 'blue', 'dark')",
            name="ck_ingredient_ledger_valid_type",
        ),
        sa.CheckConstraint(
            "change <> 0",
            name="ck_ingredient_ledger_nonzero_change",
        ),
    )

    op.create_index(
        "ix_ingredient_ledger_entries_type",
        "ingredient_ledger_entries",
        ["ingredient_type"],
    )

    op.create_table(
        "potion_ledger_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("transaction_id", sa.Integer(), nullable=False),
        sa.Column("potion_id", sa.Integer(), nullable=False),
        sa.Column("change", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["inventory_transactions.id"],
            name="fk_potion_ledger_entries_transaction_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["potion_id"],
            ["potions.id"],
            name="fk_potion_ledger_entries_potion_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "transaction_id",
            "potion_id",
            name="uq_potion_ledger_transaction_potion",
        ),
        sa.CheckConstraint(
            "change <> 0",
            name="ck_potion_ledger_nonzero_change",
        ),
    )

    op.create_index(
        "ix_potion_ledger_entries_potion_id",
        "potion_ledger_entries",
        ["potion_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_potion_ledger_entries_potion_id",
        table_name="potion_ledger_entries",
    )
    op.drop_table("potion_ledger_entries")

    op.drop_index(
        "ix_ingredient_ledger_entries_type",
        table_name="ingredient_ledger_entries",
    )
    op.drop_table("ingredient_ledger_entries")

    op.drop_table("gold_ledger_entries")
    op.drop_table("processed_requests")

    op.drop_index(
        "ix_inventory_transactions_created_at",
        table_name="inventory_transactions",
    )
    op.drop_table("inventory_transactions")
    op.drop_table("game_time")
