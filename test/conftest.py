from collections.abc import Iterator

import pytest
import sqlalchemy
from sqlalchemy.engine import Engine


@pytest.fixture
def v3_engine() -> Iterator[Engine]:
    engine = sqlalchemy.create_engine("sqlite://")

    statements = [
        """
        CREATE TABLE global_inventory (
            id INTEGER PRIMARY KEY
        )
        """,
        """
        CREATE TABLE potions (
            id INTEGER PRIMARY KEY,
            sku TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 0,
            price INTEGER NOT NULL,
            red_ml INTEGER NOT NULL,
            green_ml INTEGER NOT NULL,
            blue_ml INTEGER NOT NULL,
            dark_ml INTEGER NOT NULL
        )
        """,
        """
        CREATE TABLE carts (
            id INTEGER PRIMARY KEY,
            customer_id TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            character_class TEXT NOT NULL,
            character_species TEXT NOT NULL,
            level INTEGER NOT NULL,
            payment TEXT,
            checked_out BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            checked_out_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE cart_items (
            id INTEGER PRIMARY KEY,
            cart_id INTEGER NOT NULL,
            potion_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            UNIQUE (cart_id, potion_id)
        )
        """,
        """
        CREATE TABLE game_time (
            id INTEGER PRIMARY KEY,
            day TEXT,
            hour INTEGER,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE inventory_transactions (
            id INTEGER PRIMARY KEY,
            transaction_type TEXT NOT NULL,
            cart_id INTEGER,
            description TEXT,
            game_day TEXT,
            game_hour INTEGER,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE processed_requests (
            id INTEGER PRIMARY KEY,
            operation_type TEXT NOT NULL,
            request_id TEXT NOT NULL,
            transaction_id INTEGER,
            response_status INTEGER,
            response_body JSON,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (operation_type, request_id)
        )
        """,
        """
        CREATE TABLE gold_ledger_entries (
            id INTEGER PRIMARY KEY,
            transaction_id INTEGER NOT NULL,
            change INTEGER NOT NULL
        )
        """,
        """
        CREATE TABLE ingredient_ledger_entries (
            id INTEGER PRIMARY KEY,
            transaction_id INTEGER NOT NULL,
            ingredient_type TEXT NOT NULL,
            change INTEGER NOT NULL,
            UNIQUE (transaction_id, ingredient_type)
        )
        """,
        """
        CREATE TABLE potion_ledger_entries (
            id INTEGER PRIMARY KEY,
            transaction_id INTEGER NOT NULL,
            potion_id INTEGER NOT NULL,
            change INTEGER NOT NULL,
            UNIQUE (transaction_id, potion_id)
        )
        """,
    ]

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(sqlalchemy.text(statement))

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO global_inventory (id)
                VALUES (1)
                """
            )
        )
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO game_time (id, day, hour)
                VALUES (1, NULL, NULL)
                """
            )
        )

    yield engine
    engine.dispose()
