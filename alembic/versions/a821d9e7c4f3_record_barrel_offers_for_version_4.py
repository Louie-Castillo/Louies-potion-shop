"""record barrel offers for version 4

Revision ID: a821d9e7c4f3
Revises: cba3f48cb2af
Create Date: 2026-09-21 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a821d9e7c4f3"
down_revision: Union[str, None] = "cba3f48cb2af"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "barrel_offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_day", sa.String(length=20), nullable=False),
        sa.Column("game_hour", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("ml_per_barrel", sa.Integer(), nullable=False),
        sa.Column("red_fraction", sa.Float(), nullable=False),
        sa.Column("green_fraction", sa.Float(), nullable=False),
        sa.Column("blue_fraction", sa.Float(), nullable=False),
        sa.Column("dark_fraction", sa.Float(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "offered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "game_hour >= 0 AND game_hour <= 23",
            name="ck_barrel_offers_valid_game_hour",
        ),
        sa.CheckConstraint(
            "ml_per_barrel > 0",
            name="ck_barrel_offers_positive_ml",
        ),
        sa.CheckConstraint(
            "price >= 0",
            name="ck_barrel_offers_nonnegative_price",
        ),
        sa.CheckConstraint(
            "quantity >= 0",
            name="ck_barrel_offers_nonnegative_quantity",
        ),
        sa.CheckConstraint(
            """
            red_fraction >= 0 AND red_fraction <= 1
            AND green_fraction >= 0 AND green_fraction <= 1
            AND blue_fraction >= 0 AND blue_fraction <= 1
            AND dark_fraction >= 0 AND dark_fraction <= 1
            """,
            name="ck_barrel_offers_valid_fractions",
        ),
        sa.UniqueConstraint(
            "game_day",
            "game_hour",
            "sku",
            "ml_per_barrel",
            "red_fraction",
            "green_fraction",
            "blue_fraction",
            "dark_fraction",
            "price",
            "quantity",
            name="uq_barrel_offer_schedule",
        ),
    )

    op.create_index(
        "ix_barrel_offers_game_time",
        "barrel_offers",
        ["game_day", "game_hour"],
    )
    op.create_index(
        "ix_barrel_offers_sku",
        "barrel_offers",
        ["sku"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_barrel_offers_sku",
        table_name="barrel_offers",
    )
    op.drop_index(
        "ix_barrel_offers_game_time",
        table_name="barrel_offers",
    )
    op.drop_table("barrel_offers")
