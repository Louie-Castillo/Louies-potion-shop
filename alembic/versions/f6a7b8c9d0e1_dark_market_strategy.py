"""add dark market strategy

Revision ID: f6a7b8c9d0e1
Revises: d4e5f6a7b8c9
Create Date: 2026-10-05 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "potions",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    # The catalog can expose at most six SKUs. Cyan has no recorded sales, so
    # replace that experimental slot with a low-cost, exact-match dark potion.
    op.execute(
        sa.text(
            """
            UPDATE potions
            SET is_active = FALSE
            WHERE sku = 'CYAN_POTION_0'
            """
        )
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
                quantity,
                is_active
            )
            VALUES (
                'dark potion',
                'DARK_POTION_0',
                45,
                0,
                0,
                0,
                100,
                0,
                TRUE
            )
            """
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    dark_potion_id = connection.execute(
        sa.text(
            """
            SELECT id
            FROM potions
            WHERE sku = 'DARK_POTION_0'
            """
        )
    ).scalar_one_or_none()

    if dark_potion_id is not None:
        connection.execute(
            sa.text(
                """
                DELETE FROM cart_items
                WHERE potion_id = :potion_id
                """
            ),
            {"potion_id": dark_potion_id},
        )
        connection.execute(
            sa.text(
                """
                DELETE FROM potion_ledger_entries
                WHERE potion_id = :potion_id
                """
            ),
            {"potion_id": dark_potion_id},
        )
        connection.execute(
            sa.text(
                """
                DELETE FROM potions
                WHERE id = :potion_id
                """
            ),
            {"potion_id": dark_potion_id},
        )

    connection.execute(
        sa.text(
            """
            UPDATE potions
            SET is_active = TRUE
            WHERE sku = 'CYAN_POTION_0'
            """
        )
    )
    op.drop_column("potions", "is_active")
