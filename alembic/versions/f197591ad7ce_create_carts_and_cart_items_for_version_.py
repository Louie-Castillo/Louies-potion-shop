"""create carts and cart items for version 2

Revision ID: f197591ad7ce
Revises: 97d99721f048
Create Date: 2026-09-07 18:51:11.869869

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f197591ad7ce"
down_revision: Union[str, None] = "97d99721f048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "carts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.String(length=255), nullable=False),
        sa.Column("customer_name", sa.String(length=255), nullable=False),
        sa.Column("character_class", sa.String(length=100), nullable=False),
        sa.Column("character_species", sa.String(length=100), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("payment", sa.String(length=255), nullable=True),
        sa.Column(
            "checked_out",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "checked_out_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            "level >= 1 AND level <= 20",
            name="ck_carts_valid_customer_level",
        ),
    )

    op.create_table(
        "cart_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cart_id", sa.Integer(), nullable=False),
        sa.Column("potion_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["cart_id"],
            ["carts.id"],
            name="fk_cart_items_cart_id_carts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["potion_id"],
            ["potions.id"],
            name="fk_cart_items_potion_id_potions",
        ),
        sa.UniqueConstraint(
            "cart_id",
            "potion_id",
            name="uq_cart_items_cart_and_potion",
        ),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_cart_items_quantity_positive",
        ),
    )


def downgrade() -> None:
    op.drop_table("cart_items")
    op.drop_table("carts")
