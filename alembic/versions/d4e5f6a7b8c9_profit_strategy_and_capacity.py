"""profit strategy and capacity

Revision ID: d4e5f6a7b8c9
Revises: a821d9e7c4f3
Create Date: 2026-10-02 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "a821d9e7c4f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "capacity_ledger_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("transaction_id", sa.Integer(), nullable=False),
        sa.Column(
            "potion_capacity_change",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "ml_capacity_change",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["inventory_transactions.id"],
            name="fk_capacity_ledger_entries_transaction_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "transaction_id",
            name="uq_capacity_ledger_entries_transaction",
        ),
        sa.CheckConstraint(
            "potion_capacity_change <> 0 OR ml_capacity_change <> 0",
            name="ck_capacity_ledger_entries_nonzero_change",
        ),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO potions (
                name,
                sku,
                price,
                red_ml,
                green_ml,
                blue_ml,
                dark_ml,
                quantity
            )
            VALUES
                ('purple potion', 'PURPLE_POTION_0', 60, 50, 0, 50, 0, 0),
                ('cyan potion', 'CYAN_POTION_0', 60, 0, 50, 50, 0, 0)
            ON CONFLICT DO NOTHING
            """
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    potion_ids = connection.execute(
        sa.text(
            """
            SELECT id
            FROM potions
            WHERE sku IN ('PURPLE_POTION_0', 'CYAN_POTION_0')
            """
        )
    ).scalars()
    potion_ids = list(potion_ids)

    if potion_ids:
        connection.execute(
            sa.text(
                """
                DELETE FROM cart_items
                WHERE potion_id IN :potion_ids
                """
            ).bindparams(sa.bindparam("potion_ids", expanding=True)),
            {"potion_ids": potion_ids},
        )
        connection.execute(
            sa.text(
                """
                DELETE FROM potion_ledger_entries
                WHERE potion_id IN :potion_ids
                """
            ).bindparams(sa.bindparam("potion_ids", expanding=True)),
            {"potion_ids": potion_ids},
        )
        connection.execute(
            sa.text(
                """
                DELETE FROM potions
                WHERE id IN :potion_ids
                """
            ).bindparams(sa.bindparam("potion_ids", expanding=True)),
            {"potion_ids": potion_ids},
        )

    op.drop_table("capacity_ledger_entries")
