import pytest
import sqlalchemy

from src.api import admin, inventory


def test_audit_and_reset_use_version_two_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_engine = sqlalchemy.create_engine("sqlite+pysqlite:///:memory:")

    with test_engine.begin() as connection:
        connection.execute(
            sqlalchemy.text(
                """
                CREATE TABLE global_inventory (
                    id INTEGER PRIMARY KEY,
                    gold INTEGER NOT NULL,
                    red_ml INTEGER NOT NULL,
                    green_ml INTEGER NOT NULL,
                    blue_ml INTEGER NOT NULL
                )
                """
            )
        )

        connection.execute(
            sqlalchemy.text(
                """
                CREATE TABLE potions (
                    id INTEGER PRIMARY KEY,
                    quantity INTEGER NOT NULL
                )
                """
            )
        )

        connection.execute(
            sqlalchemy.text(
                """
                CREATE TABLE carts (
                    id INTEGER PRIMARY KEY
                )
                """
            )
        )

        connection.execute(
            sqlalchemy.text(
                """
                CREATE TABLE cart_items (
                    id INTEGER PRIMARY KEY,
                    cart_id INTEGER NOT NULL
                )
                """
            )
        )

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO global_inventory (
                    id,
                    gold,
                    red_ml,
                    green_ml,
                    blue_ml
                )
                VALUES (1, 250, 100, 200, 300)
                """
            )
        )

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO potions (id, quantity)
                VALUES
                    (1, 2),
                    (2, 3)
                """
            )
        )

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO carts (id)
                VALUES (1)
                """
            )
        )

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO cart_items (id, cart_id)
                VALUES (1, 1)
                """
            )
        )

    monkeypatch.setattr(inventory.db, "engine", test_engine)

    audit_before_reset = inventory.get_inventory()

    assert audit_before_reset.number_of_potions == 5
    assert audit_before_reset.ml_in_barrels == 600
    assert audit_before_reset.gold == 250

    admin.reset()

    audit_after_reset = inventory.get_inventory()

    assert audit_after_reset.number_of_potions == 0
    assert audit_after_reset.ml_in_barrels == 0
    assert audit_after_reset.gold == 100

    with test_engine.begin() as connection:
        potion_state = connection.execute(
            sqlalchemy.text(
                """
                SELECT
                    COUNT(*) AS potion_types,
                    SUM(quantity) AS total_quantity
                FROM potions
                """
            )
        ).one()

        cart_count = connection.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*)
                FROM carts
                """
            )
        ).scalar_one()

        cart_item_count = connection.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*)
                FROM cart_items
                """
            )
        ).scalar_one()

    assert potion_state.potion_types == 2
    assert potion_state.total_quantity == 0
    assert cart_count == 0
    assert cart_item_count == 0

    test_engine.dispose()
