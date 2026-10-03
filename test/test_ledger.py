import sqlalchemy

from src import ledger


def test_reads_current_ledger_balances() -> None:
    engine = sqlalchemy.create_engine("sqlite+pysqlite:///:memory:")

    with engine.begin() as connection:
        connection.execute(
            sqlalchemy.text(
                """
                CREATE TABLE potions (
                    id INTEGER PRIMARY KEY
                )
                """
            )
        )

        connection.execute(
            sqlalchemy.text(
                """
                CREATE TABLE gold_ledger_entries (
                    id INTEGER PRIMARY KEY,
                    change INTEGER NOT NULL
                )
                """
            )
        )

        connection.execute(
            sqlalchemy.text(
                """
                CREATE TABLE ingredient_ledger_entries (
                    id INTEGER PRIMARY KEY,
                    ingredient_type TEXT NOT NULL,
                    change INTEGER NOT NULL
                )
                """
            )
        )

        connection.execute(
            sqlalchemy.text(
                """
                CREATE TABLE potion_ledger_entries (
                    id INTEGER PRIMARY KEY,
                    potion_id INTEGER NOT NULL,
                    change INTEGER NOT NULL
                )
                """
            )
        )
        connection.execute(
            sqlalchemy.text(
                """
                CREATE TABLE capacity_ledger_entries (
                    id INTEGER PRIMARY KEY,
                    potion_capacity_change INTEGER NOT NULL,
                    ml_capacity_change INTEGER NOT NULL
                )
                """
            )
        )

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO potions (id)
                VALUES (1), (2)
                """
            )
        )

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO gold_ledger_entries (id, change)
                VALUES
                    (1, 100),
                    (2, -25)
                """
            )
        )

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO ingredient_ledger_entries (
                    id,
                    ingredient_type,
                    change
                )
                VALUES
                    (1, 'red', 1000),
                    (2, 'red', -100),
                    (3, 'green', 500)
                """
            )
        )

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO potion_ledger_entries (
                    id,
                    potion_id,
                    change
                )
                VALUES
                    (1, 1, 4),
                    (2, 1, -1)
                """
            )
        )

        gold = ledger.get_current_gold(connection)
        ingredients = ledger.get_current_ingredients(connection)
        potion_quantities = ledger.get_current_potion_quantities(connection)
        total_potions = ledger.get_total_potions(connection)
        capacity = ledger.get_capacity_balances(connection)

    assert gold == 75

    assert ingredients.red_ml == 900
    assert ingredients.green_ml == 500
    assert ingredients.blue_ml == 0
    assert ingredients.dark_ml == 0
    assert ingredients.total_ml == 1400

    assert potion_quantities == {
        1: 3,
        2: 0,
    }

    assert total_potions == 3
    assert capacity.potion_units == 1
    assert capacity.ml_units == 1
    assert capacity.maximum_potions == 50
    assert capacity.maximum_ml == 10000

    engine.dispose()


def test_recent_sales_receive_more_demand_weight() -> None:
    engine = sqlalchemy.create_engine("sqlite+pysqlite:///:memory:")

    with engine.begin() as connection:
        connection.execute(
            sqlalchemy.text(
                """
                CREATE TABLE inventory_transactions (
                    id INTEGER PRIMARY KEY,
                    transaction_type TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )
        )
        connection.execute(
            sqlalchemy.text(
                """
                CREATE TABLE potion_ledger_entries (
                    id INTEGER PRIMARY KEY,
                    transaction_id INTEGER NOT NULL,
                    potion_id INTEGER NOT NULL,
                    change INTEGER NOT NULL
                )
                """
            )
        )
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO inventory_transactions (
                    id,
                    transaction_type,
                    created_at
                )
                VALUES
                    (1, 'checkout', '2026-09-01 12:00:00'),
                    (2, 'checkout', '2026-09-20 12:00:00'),
                    (3, 'checkout', '2026-09-30 12:00:00'),
                    (4, 'bottle_delivery', '2026-09-30 12:00:00')
                """
            )
        )
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO potion_ledger_entries (
                    id,
                    transaction_id,
                    potion_id,
                    change
                )
                VALUES
                    (1, 1, 1, -10),
                    (2, 2, 1, -2),
                    (3, 3, 2, -3),
                    (4, 4, 2, 50)
                """
            )
        )

        demand = ledger.get_potion_sales_quantities(connection)

    assert demand == {1: 14, 2: 12}

    engine.dispose()
