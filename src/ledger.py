from dataclasses import dataclass
from datetime import datetime, timezone

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


BASE_POTION_CAPACITY = 50
BASE_ML_CAPACITY = 10000
CAPACITY_UNIT_COST = 1000
MAX_CAPACITY_UNITS = 10


@dataclass(frozen=True)
class CapacityBalances:
    potion_units: int
    ml_units: int

    @property
    def maximum_potions(self) -> int:
        return self.potion_units * BASE_POTION_CAPACITY

    @property
    def maximum_ml(self) -> int:
        return self.ml_units * BASE_ML_CAPACITY


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


def get_capacity_balances(connection: Connection) -> CapacityBalances:
    row = connection.execute(
        sqlalchemy.text(
            """
            SELECT
                1 + COALESCE(SUM(potion_capacity_change), 0)
                    AS potion_units,
                1 + COALESCE(SUM(ml_capacity_change), 0)
                    AS ml_units
            FROM capacity_ledger_entries
            """
        )
    ).one()

    return CapacityBalances(
        potion_units=int(row.potion_units),
        ml_units=int(row.ml_units),
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


def get_potion_sales_quantities(connection: Connection) -> dict[int, int]:
    rows = connection.execute(
        sqlalchemy.text(
            """
            SELECT
                ple.potion_id,
                -ple.change AS units_sold,
                transactions.created_at
            FROM inventory_transactions AS transactions
            JOIN potion_ledger_entries AS ple
                ON ple.transaction_id = transactions.id
            WHERE
                transactions.transaction_type = 'checkout'
                AND ple.change < 0
            ORDER BY transactions.created_at, ple.potion_id
            """
        )
    ).all()

    if not rows:
        return {}

    def parse_timestamp(value: object) -> datetime:
        if isinstance(value, datetime):
            parsed = value
        else:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    latest_timestamp = max(parse_timestamp(row.created_at) for row in rows)
    weighted_demand: dict[int, int] = {}

    for row in rows:
        age_days = (latest_timestamp - parse_timestamp(row.created_at)).days
        if age_days <= 7:
            recency_weight = 4
        elif age_days <= 14:
            recency_weight = 2
        else:
            recency_weight = 1

        potion_id = int(row.potion_id)
        weighted_demand[potion_id] = weighted_demand.get(potion_id, 0) + (
            int(row.units_sold) * recency_weight
        )

    return weighted_demand


def get_ingredient_cost_per_ml(connection: Connection) -> dict[str, float]:
    row = connection.execute(
        sqlalchemy.text(
            """
            SELECT
                MIN(
                    CASE WHEN red_fraction > 0
                    THEN price * 1.0 / (ml_per_barrel * red_fraction)
                    END
                ) AS red_cost,
                MIN(
                    CASE WHEN green_fraction > 0
                    THEN price * 1.0 / (ml_per_barrel * green_fraction)
                    END
                ) AS green_cost,
                MIN(
                    CASE WHEN blue_fraction > 0
                    THEN price * 1.0 / (ml_per_barrel * blue_fraction)
                    END
                ) AS blue_cost,
                MIN(
                    CASE WHEN dark_fraction > 0
                    THEN price * 1.0 / (ml_per_barrel * dark_fraction)
                    END
                ) AS dark_cost
            FROM barrel_offers
            """
        )
    ).one()

    costs = {
        "red": row.red_cost,
        "green": row.green_cost,
        "blue": row.blue_cost,
        "dark": row.dark_cost,
    }
    return {color: float(cost) for color, cost in costs.items() if cost is not None}


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
