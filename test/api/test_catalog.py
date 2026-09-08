import pytest
import sqlalchemy

from src.api import catalog


def test_catalog_returns_in_stock_database_potions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_engine = sqlalchemy.create_engine("sqlite+pysqlite:///:memory:")

    with test_engine.begin() as connection:
        connection.execute(
            sqlalchemy.text(
                """
                CREATE TABLE potions (
                    id INTEGER PRIMARY KEY,
                    sku TEXT NOT NULL,
                    name TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price INTEGER NOT NULL,
                    red_ml INTEGER NOT NULL,
                    green_ml INTEGER NOT NULL,
                    blue_ml INTEGER NOT NULL,
                    dark_ml INTEGER NOT NULL
                )
                """
            )
        )

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO potions (
                    id,
                    sku,
                    name,
                    quantity,
                    price,
                    red_ml,
                    green_ml,
                    blue_ml,
                    dark_ml
                )
                VALUES (
                    :id,
                    :sku,
                    :name,
                    :quantity,
                    :price,
                    :red_ml,
                    :green_ml,
                    :blue_ml,
                    :dark_ml
                )
                """
            ),
            [
                {
                    "id": 1,
                    "sku": "RED_POTION_0",
                    "name": "red potion",
                    "quantity": 0,
                    "price": 50,
                    "red_ml": 100,
                    "green_ml": 0,
                    "blue_ml": 0,
                    "dark_ml": 0,
                },
                {
                    "id": 2,
                    "sku": "YELLOW_POTION_0",
                    "name": "yellow potion",
                    "quantity": 3,
                    "price": 60,
                    "red_ml": 50,
                    "green_ml": 50,
                    "blue_ml": 0,
                    "dark_ml": 0,
                },
            ],
        )

    monkeypatch.setattr(catalog.db, "engine", test_engine)

    result = catalog.create_catalog()

    assert len(result) == 1

    yellow_potion = result[0]

    assert yellow_potion.sku == "YELLOW_POTION_0"
    assert yellow_potion.name == "yellow potion"
    assert yellow_potion.quantity == 3
    assert yellow_potion.price == 60
    assert yellow_potion.potion_type == [50, 50, 0, 0]

    test_engine.dispose()
