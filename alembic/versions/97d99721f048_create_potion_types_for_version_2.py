"""create potion types for version 2

Revision ID: 97d99721f048
Revises: 6fd3f8128fc6
Create Date: 2026-09-07 16:58:36.546343

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "97d99721f048"
down_revision: Union[str, None] = "6fd3f8128fc6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    potions_table = op.create_table(
        "potions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sku", sa.String(length=20), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("red_ml", sa.Integer(), nullable=False),
        sa.Column("green_ml", sa.Integer(), nullable=False),
        sa.Column("blue_ml", sa.Integer(), nullable=False),
        sa.Column("dark_ml", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("sku", name="uq_potions_sku"),
        sa.UniqueConstraint(
            "red_ml", "green_ml", "blue_ml", "dark_ml", name="uq_potions_mixture"
        ),
        sa.CheckConstraint("red_ml >= 0", name="ck_potions_red_ml_non_negative"),
        sa.CheckConstraint("green_ml >= 0", name="ck_potions_green_ml_non_negative"),
        sa.CheckConstraint("blue_ml >= 0", name="ck_potions_blue_ml_non_negative"),
        sa.CheckConstraint("dark_ml >= 0", name="ck_potions_dark_ml_non_negative"),
        sa.CheckConstraint(
            "price >= 1 AND price <= 500", name="ck_potions_valid_price"
        ),
        sa.CheckConstraint("quantity >= 0", name="ck_potions_quantity_non_negative"),
        sa.CheckConstraint(
            "red_ml + green_ml + blue_ml + dark_ml = 100",
            name="ck_potions_mixture_totals_100",
        ),
    )

    op.bulk_insert(
        potions_table,
        [
            {
                "name": "red potion",
                "sku": "RED_POTION_0",
                "price": 50,
                "red_ml": 100,
                "green_ml": 0,
                "blue_ml": 0,
                "dark_ml": 0,
                "quantity": 0,
            },
            {
                "name": "green potion",
                "sku": "GREEN_POTION_0",
                "price": 50,
                "red_ml": 0,
                "green_ml": 100,
                "blue_ml": 0,
                "dark_ml": 0,
                "quantity": 0,
            },
            {
                "name": "blue potion",
                "sku": "BLUE_POTION_0",
                "price": 50,
                "red_ml": 0,
                "green_ml": 0,
                "blue_ml": 100,
                "dark_ml": 0,
                "quantity": 0,
            },
            {
                "name": "yellow potion",
                "sku": "YELLOW_POTION_0",
                "price": 60,
                "red_ml": 50,
                "green_ml": 50,
                "blue_ml": 0,
                "dark_ml": 0,
                "quantity": 0,
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("potions")
