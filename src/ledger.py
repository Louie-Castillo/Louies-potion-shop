from dataclasses import dataclass

import sqlalchemy
from sqlalchemy.engine import Connection


@dataclass(frozen=True)
class IngredientBalances:
    red_ml: int
    green_ml: int
    blue_ml: int
    dark_ml: int

    @property
    def total_ml(self) -> int:
        return self.red_ml + self.green_ml + self.blue_ml + self.dark_ml


def get_current_gold(connection: Connection) -> int:
    result = connection.execute(
        sqlalchemy.text(
            """
            SELECT COALESCE(SUM(change), 0)
            FROM gold_ledger_entries
            """
        )
    ).scalar_one()

    return int(result)


def get_current_ingredients(
    connection: Connection,
) -> IngredientBalances:
    row = connection.execute(
        sqlalchemy.text(
            """
            SELECT
                COALESCE(
                    SUM(
                        CASE
                            WHEN ingredient_type = 'red'
                            THEN change
                            ELSE 0
                        END
                    ),
                    0
                ) AS red_ml,
                COALESCE(
                    SUM(
                        CASE
                            WHEN ingredient_type = 'green'
                            THEN change
                            ELSE 0
                        END
                    ),
                    0
                ) AS green_ml,
                COALESCE(
                    SUM(
                        CASE
                            WHEN ingredient_type = 'blue'
                            THEN change
                            ELSE 0
                        END
                    ),
                    0
                ) AS blue_ml,
                COALESCE(
                    SUM(
                        CASE
                            WHEN ingredient_type = 'dark'
                            THEN change
                            ELSE 0
                        END
                    ),
                    0
                ) AS dark_ml
            FROM ingredient_ledger_entries
            """
        )
    ).one()

    return IngredientBalances(
        red_ml=int(row.red_ml),
        green_ml=int(row.green_ml),
        blue_ml=int(row.blue_ml),
        dark_ml=int(row.dark_ml),
    )


def get_current_potion_quantities(
    connection: Connection,
) -> dict[int, int]:
    rows = connection.execute(
        sqlalchemy.text(
            """
            SELECT
                p.id AS potion_id,
                COALESCE(SUM(ple.change), 0) AS quantity
            FROM potions AS p
            LEFT JOIN potion_ledger_entries AS ple
                ON ple.potion_id = p.id
            GROUP BY p.id
            ORDER BY p.id
            """
        )
    ).all()

    return {int(row.potion_id): int(row.quantity) for row in rows}


def get_total_potions(connection: Connection) -> int:
    result = connection.execute(
        sqlalchemy.text(
            """
            SELECT COALESCE(SUM(change), 0)
            FROM potion_ledger_entries
            """
        )
    ).scalar_one()

    return int(result)
