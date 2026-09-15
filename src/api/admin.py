from fastapi import APIRouter, Depends, status
import sqlalchemy
from src.api import auth
from src import database as db
from src import ledger

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(auth.get_api_key)],
)


@router.post("/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset() -> None:
    """
    Reset the game state. Gold goes to 100, all potions are removed from
    inventory, and all raw ingredients are removed. Open carts are deleted,
    while checked-out carts remain available as sales history.
    """
    with db.engine.begin() as connection:
        lock_query = """
            SELECT id
            FROM global_inventory
            WHERE id = 1
        """

        if connection.dialect.name == "postgresql":
            lock_query += " FOR UPDATE"

        connection.execute(sqlalchemy.text(lock_query)).one()

        gold = ledger.get_current_gold(connection)
        ingredients = ledger.get_current_ingredients(connection)
        potion_quantities = ledger.get_current_potion_quantities(connection)

        gold_change = 100 - gold
        ingredient_changes = {
            "red": -ingredients.red_ml,
            "green": -ingredients.green_ml,
            "blue": -ingredients.blue_ml,
            "dark": -ingredients.dark_ml,
        }
        potion_changes = {
            potion_id: -quantity
            for potion_id, quantity in potion_quantities.items()
            if quantity != 0
        }

        has_balance_changes = (
            gold_change != 0
            or any(change != 0 for change in ingredient_changes.values())
            or bool(potion_changes)
        )

        if has_balance_changes:
            transaction_id = int(
                connection.execute(
                    sqlalchemy.text(
                        """
                        INSERT INTO inventory_transactions (
                            transaction_type,
                            description
                        )
                        VALUES (
                            'reset',
                            'Reset inventory balances'
                        )
                        RETURNING id
                        """
                    )
                ).scalar_one()
            )

            if gold_change != 0:
                connection.execute(
                    sqlalchemy.text(
                        """
                        INSERT INTO gold_ledger_entries (
                            transaction_id,
                            change
                        )
                        VALUES (
                            :transaction_id,
                            :change
                        )
                        """
                    ),
                    {
                        "transaction_id": transaction_id,
                        "change": gold_change,
                    },
                )

            ingredient_entries: list[dict[str, object]] = [
                {
                    "transaction_id": transaction_id,
                    "ingredient_type": ingredient_type,
                    "change": change,
                }
                for ingredient_type, change in ingredient_changes.items()
                if change != 0
            ]

            if ingredient_entries:
                connection.execute(
                    sqlalchemy.text(
                        """
                        INSERT INTO ingredient_ledger_entries (
                            transaction_id,
                            ingredient_type,
                            change
                        )
                        VALUES (
                            :transaction_id,
                            :ingredient_type,
                            :change
                        )
                        """
                    ),
                    ingredient_entries,
                )

            if potion_changes:
                connection.execute(
                    sqlalchemy.text(
                        """
                        INSERT INTO potion_ledger_entries (
                            transaction_id,
                            potion_id,
                            change
                        )
                        VALUES (
                            :transaction_id,
                            :potion_id,
                            :change
                        )
                        """
                    ),
                    [
                        {
                            "transaction_id": transaction_id,
                            "potion_id": potion_id,
                            "change": change,
                        }
                        for potion_id, change in potion_changes.items()
                    ],
                )

        connection.execute(
            sqlalchemy.text(
                """
                DELETE FROM cart_items
                WHERE cart_id IN (
                    SELECT id
                    FROM carts
                    WHERE checked_out = FALSE
                )
                """
            )
        )

        connection.execute(
            sqlalchemy.text(
                """
                DELETE FROM carts
                WHERE checked_out = FALSE
                """
            )
        )

        connection.execute(
            sqlalchemy.text(
                """
                DELETE FROM processed_requests
                """
            )
        )

        connection.execute(
            sqlalchemy.text(
                """
                UPDATE game_time
                SET
                    day = NULL,
                    hour = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
                    AND (day IS NOT NULL OR hour IS NOT NULL)
                """
            )
        )
