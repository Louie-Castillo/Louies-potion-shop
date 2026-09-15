"""ledger balances

Revision ID: cba3f48cb2af
Revises: 6c6fb143773b
Create Date: 2026-09-14 21:42:48.040181

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "cba3f48cb2af"
down_revision: Union[str, None] = "6c6fb143773b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()

    transaction_id = connection.execute(
        sa.text(
            """
            INSERT INTO inventory_transactions (
                transaction_type,
                description
            )
            VALUES (
                'opening_balance',
                'Opening balances copied from Version 2'
            )
            RETURNING id
            """
        )
    ).scalar_one()

    connection.execute(
        sa.text(
            """
            INSERT INTO gold_ledger_entries (
                transaction_id,
                change
            )
            SELECT
                :transaction_id,
                gold
            FROM global_inventory
            WHERE
                id = 1
                AND gold <> 0
            """
        ),
        {"transaction_id": transaction_id},
    )

    connection.execute(
        sa.text(
            """
            INSERT INTO ingredient_ledger_entries (
                transaction_id,
                ingredient_type,
                change
            )
            SELECT
                :transaction_id,
                ingredient_type,
                amount
            FROM (
                SELECT
                    'red' AS ingredient_type,
                    red_ml AS amount
                FROM global_inventory
                WHERE id = 1

                UNION ALL

                SELECT
                    'green' AS ingredient_type,
                    green_ml AS amount
                FROM global_inventory
                WHERE id = 1

                UNION ALL

                SELECT
                    'blue' AS ingredient_type,
                    blue_ml AS amount
                FROM global_inventory
                WHERE id = 1
            ) AS opening_ingredients
            WHERE amount <> 0
            """
        ),
        {"transaction_id": transaction_id},
    )

    connection.execute(
        sa.text(
            """
            INSERT INTO potion_ledger_entries (
                transaction_id,
                potion_id,
                change
            )
            SELECT
                :transaction_id,
                id,
                quantity
            FROM potions
            WHERE quantity <> 0
            """
        ),
        {"transaction_id": transaction_id},
    )


def downgrade() -> None:
    connection = op.get_bind()

    connection.execute(
        sa.text(
            """
            DELETE FROM potion_ledger_entries
            WHERE transaction_id IN (
                SELECT id
                FROM inventory_transactions
                WHERE
                    transaction_type = 'opening_balance'
                    AND description =
                        'Opening balances copied from Version 2'
            )
            """
        )
    )

    connection.execute(
        sa.text(
            """
            DELETE FROM ingredient_ledger_entries
            WHERE transaction_id IN (
                SELECT id
                FROM inventory_transactions
                WHERE
                    transaction_type = 'opening_balance'
                    AND description =
                        'Opening balances copied from Version 2'
            )
            """
        )
    )

    connection.execute(
        sa.text(
            """
            DELETE FROM gold_ledger_entries
            WHERE transaction_id IN (
                SELECT id
                FROM inventory_transactions
                WHERE
                    transaction_type = 'opening_balance'
                    AND description =
                        'Opening balances copied from Version 2'
            )
            """
        )
    )

    connection.execute(
        sa.text(
            """
            DELETE FROM inventory_transactions
            WHERE
                transaction_type = 'opening_balance'
                AND description =
                    'Opening balances copied from Version 2'
            """
        )
    )
