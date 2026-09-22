from typing import List

import pytest
import sqlalchemy
from fastapi import HTTPException, status
from sqlalchemy.engine import Engine

from src.api import barrels as barrels_api
from src.api.barrels import (
    Barrel,
    BarrelOrder,
    calculate_barrel_summary,
    create_barrel_plan,
)


def create_barrel_delivery_test_engine(
    gold: int,
    ingredient_balances: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> Engine:
    test_engine = sqlalchemy.create_engine("sqlite://")

    with test_engine.begin() as connection:
        connection.execute(
            sqlalchemy.text(
                """
                CREATE TABLE global_inventory (
                    id INTEGER PRIMARY KEY
                )
                """
            )
        )
        connection.execute(
            sqlalchemy.text(
                """
                CREATE TABLE inventory_transactions (
                    id INTEGER PRIMARY KEY,
                    transaction_type TEXT NOT NULL,
                    description TEXT
                )
                """
            )
        )
        connection.execute(
            sqlalchemy.text(
                """
                CREATE TABLE processed_requests (
                    id INTEGER PRIMARY KEY,
                    operation_type TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    transaction_id INTEGER,
                    response_status INTEGER,
                    response_body JSON,
                    UNIQUE (operation_type, request_id)
                )
                """
            )
        )
        connection.execute(
            sqlalchemy.text(
                """
                CREATE TABLE gold_ledger_entries (
                    id INTEGER PRIMARY KEY,
                    transaction_id INTEGER NOT NULL,
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
                    transaction_id INTEGER NOT NULL,
                    ingredient_type TEXT NOT NULL,
                    change INTEGER NOT NULL
                )
                """
            )
        )

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO global_inventory (id)
                VALUES (1)
                """
            )
        )
        opening_transaction_id = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO inventory_transactions (
                    transaction_type,
                    description
                )
                VALUES (
                    'opening_balance',
                    'Test opening balance'
                )
                RETURNING id
                """
            )
        ).scalar_one()

        if gold != 0:
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
                    "transaction_id": opening_transaction_id,
                    "change": gold,
                },
            )

        ingredient_entries: list[dict[str, object]] = [
            {
                "transaction_id": opening_transaction_id,
                "ingredient_type": ingredient_type,
                "change": balance,
            }
            for ingredient_type, balance in zip(
                ("red", "green", "blue", "dark"),
                ingredient_balances,
            )
            if balance != 0
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

    return test_engine


def red_barrel(price: int = 100) -> Barrel:
    return Barrel(
        sku="SMALL_RED_BARREL",
        ml_per_barrel=1000,
        potion_type=[1.0, 0, 0, 0],
        price=price,
        quantity=1,
    )


def test_calculate_barrel_delivery_summary() -> None:
    delivery: List[Barrel] = [
        Barrel(
            sku="SMALL_RED_BARREL",
            ml_per_barrel=1000,
            potion_type=[1.0, 0, 0, 0],
            price=100,
            quantity=10,
        ),
        Barrel(
            sku="SMALL_GREEN_BARREL",
            ml_per_barrel=1000,
            potion_type=[0, 1.0, 0, 0],
            price=150,
            quantity=5,
        ),
    ]

    delivery_summary = calculate_barrel_summary(delivery)

    assert delivery_summary.gold_paid == 1750


def test_barrel_delivery_writes_ledger_entries_only_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_engine = create_barrel_delivery_test_engine(gold=500)
    monkeypatch.setattr(barrels_api.db, "engine", test_engine)

    delivery = [red_barrel()]

    assert barrels_api.post_deliver_barrels(delivery, order_id=77) is None
    assert barrels_api.post_deliver_barrels(delivery, order_id=77) is None

    with test_engine.begin() as connection:
        gold_balance = connection.execute(
            sqlalchemy.text(
                """
                SELECT COALESCE(SUM(change), 0)
                FROM gold_ledger_entries
                """
            )
        ).scalar_one()
        red_balance = connection.execute(
            sqlalchemy.text(
                """
                SELECT COALESCE(SUM(change), 0)
                FROM ingredient_ledger_entries
                WHERE ingredient_type = 'red'
                """
            )
        ).scalar_one()
        delivery_transaction_count = connection.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*)
                FROM inventory_transactions
                WHERE transaction_type = 'barrel_delivery'
                """
            )
        ).scalar_one()
        processed_request = connection.execute(
            sqlalchemy.text(
                """
                SELECT response_status, transaction_id
                FROM processed_requests
                WHERE
                    operation_type = 'barrel_delivery'
                    AND request_id = '77'
                """
            )
        ).one()

    assert gold_balance == 400
    assert red_balance == 1000
    assert delivery_transaction_count == 1
    assert processed_request.response_status == 204
    assert processed_request.transaction_id is not None


def test_barrel_delivery_retry_returns_stored_insufficient_gold_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_engine = create_barrel_delivery_test_engine(gold=50)
    monkeypatch.setattr(barrels_api.db, "engine", test_engine)

    delivery = [red_barrel()]

    with pytest.raises(HTTPException) as first_error:
        barrels_api.post_deliver_barrels(delivery, order_id=88)

    with test_engine.begin() as connection:
        credit_transaction_id = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO inventory_transactions (
                    transaction_type,
                    description
                )
                VALUES (
                    'test_credit',
                    'Gold added after failed delivery'
                )
                RETURNING id
                """
            )
        ).scalar_one()
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO gold_ledger_entries (
                    transaction_id,
                    change
                )
                VALUES (
                    :transaction_id,
                    100
                )
                """
            ),
            {"transaction_id": credit_transaction_id},
        )

    with pytest.raises(HTTPException) as retry_error:
        barrels_api.post_deliver_barrels(delivery, order_id=88)

    assert first_error.value.status_code == status.HTTP_409_CONFLICT
    assert retry_error.value.status_code == first_error.value.status_code
    assert retry_error.value.detail == first_error.value.detail

    with test_engine.begin() as connection:
        delivery_transaction_count = connection.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*)
                FROM inventory_transactions
                WHERE transaction_type = 'barrel_delivery'
                """
            )
        ).scalar_one()
        ingredient_entry_count = connection.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*)
                FROM ingredient_ledger_entries
                """
            )
        ).scalar_one()

    assert delivery_transaction_count == 0
    assert ingredient_entry_count == 0


def test_barrel_delivery_rejects_insufficient_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_engine = create_barrel_delivery_test_engine(
        gold=500,
        ingredient_balances=(9500, 0, 0, 0),
    )
    monkeypatch.setattr(barrels_api.db, "engine", test_engine)

    with pytest.raises(HTTPException) as error:
        barrels_api.post_deliver_barrels([red_barrel()], order_id=99)

    assert error.value.status_code == status.HTTP_409_CONFLICT
    assert error.value.detail == "Not enough capacity for this barrel delivery"

    with test_engine.begin() as connection:
        delivery_transaction_count = connection.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*)
                FROM inventory_transactions
                WHERE transaction_type = 'barrel_delivery'
                """
            )
        ).scalar_one()

    assert delivery_transaction_count == 0


def test_buy_barrel_for_mixed_potion_plan() -> None:
    wholesale_catalog: List[Barrel] = [
        Barrel(
            sku="SMALL_RED_BARREL",
            ml_per_barrel=1000,
            potion_type=[1.0, 0, 0, 0],
            price=100,
            quantity=10,
        ),
        Barrel(
            sku="SMALL_GREEN_BARREL",
            ml_per_barrel=1000,
            potion_type=[0, 1.0, 0, 0],
            price=150,
            quantity=5,
        ),
        Barrel(
            sku="SMALL_BLUE_BARREL",
            ml_per_barrel=1000,
            potion_type=[0, 0, 1.0, 0],
            price=500,
            quantity=2,
        ),
    ]

    barrel_orders = create_barrel_plan(
        gold=500,
        max_barrel_capacity=10000,
        current_ml=[0, 0, 0, 0],
        target_potion_type=[50, 50, 0, 0],
        wholesale_catalog=wholesale_catalog,
    )

    assert len(barrel_orders) == 1
    assert barrel_orders[0].quantity == 1

    assert barrel_orders[0].sku == "SMALL_RED_BARREL"


def test_cant_afford_barrel_plan() -> None:
    wholesale_catalog: List[Barrel] = [
        Barrel(
            sku="SMALL_RED_BARREL",
            ml_per_barrel=1000,
            potion_type=[1.0, 0, 0, 0],
            price=100,
            quantity=10,
        ),
        Barrel(
            sku="SMALL_GREEN_BARREL",
            ml_per_barrel=1000,
            potion_type=[0, 1.0, 0, 0],
            price=150,
            quantity=5,
        ),
        Barrel(
            sku="SMALL_BLUE_BARREL",
            ml_per_barrel=1000,
            potion_type=[0, 0, 1.0, 0],
            price=500,
            quantity=2,
        ),
    ]

    barrel_orders = create_barrel_plan(
        gold=50,
        max_barrel_capacity=10000,
        current_ml=[0, 1000, 1000, 0],
        target_potion_type=[50, 50, 0, 0],
        wholesale_catalog=wholesale_catalog,
    )

    assert isinstance(barrel_orders, list)
    assert all(isinstance(order, BarrelOrder) for order in barrel_orders)
    assert len(barrel_orders) == 0


def test_barrel_plan_records_each_offer_once_per_game_time(
    monkeypatch: pytest.MonkeyPatch,
    v3_engine: Engine,
) -> None:
    with v3_engine.begin() as connection:
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE game_time
                SET day = 'Edgeday', hour = 8
                WHERE id = 1
                """
            )
        )

    monkeypatch.setattr(barrels_api.db, "engine", v3_engine)

    wholesale_catalog = [
        red_barrel(price=100),
        Barrel(
            sku="SMALL_YELLOW_BARREL",
            ml_per_barrel=500,
            potion_type=[0.5, 0.5, 0, 0],
            price=75,
            quantity=3,
        ),
    ]

    assert barrels_api.get_wholesale_purchase_plan(wholesale_catalog) == []
    assert barrels_api.get_wholesale_purchase_plan(wholesale_catalog) == []

    with v3_engine.begin() as connection:
        first_tick_offers = connection.execute(
            sqlalchemy.text(
                """
                SELECT
                    game_day,
                    game_hour,
                    sku,
                    ml_per_barrel,
                    red_fraction,
                    green_fraction,
                    blue_fraction,
                    dark_fraction,
                    price,
                    quantity
                FROM barrel_offers
                ORDER BY sku
                """
            )
        ).all()

        connection.execute(
            sqlalchemy.text(
                """
                UPDATE game_time
                SET hour = 10
                WHERE id = 1
                """
            )
        )

    assert len(first_tick_offers) == 2

    red_offer = next(row for row in first_tick_offers if row.sku == "SMALL_RED_BARREL")
    yellow_offer = next(
        row for row in first_tick_offers if row.sku == "SMALL_YELLOW_BARREL"
    )

    assert red_offer.game_day == "Edgeday"
    assert red_offer.game_hour == 8
    assert red_offer.ml_per_barrel == 1000
    assert red_offer.red_fraction == 1.0
    assert red_offer.green_fraction == 0.0
    assert red_offer.price == 100
    assert red_offer.quantity == 1

    assert yellow_offer.game_day == "Edgeday"
    assert yellow_offer.game_hour == 8
    assert yellow_offer.ml_per_barrel == 500
    assert yellow_offer.red_fraction == 0.5
    assert yellow_offer.green_fraction == 0.5
    assert yellow_offer.blue_fraction == 0.0
    assert yellow_offer.dark_fraction == 0.0
    assert yellow_offer.price == 75
    assert yellow_offer.quantity == 3

    assert barrels_api.get_wholesale_purchase_plan(wholesale_catalog) == []

    with v3_engine.begin() as connection:
        offer_count = connection.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*)
                FROM barrel_offers
                """
            )
        ).scalar_one()

    assert offer_count == 4


def test_barrel_plan_reads_ledger_balances(
    monkeypatch: pytest.MonkeyPatch,
    v3_engine: Engine,
) -> None:
    with v3_engine.begin() as connection:
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
                    1,
                    'RED_POTION_0',
                    'red potion',
                    999,
                    50,
                    100,
                    0,
                    0,
                    0
                )
                """
            )
        )
        transaction_id = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO inventory_transactions (
                    transaction_type,
                    description
                )
                VALUES ('opening_balance', 'Test opening balance')
                RETURNING id
                """
            )
        ).scalar_one()
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO gold_ledger_entries (
                    transaction_id,
                    change
                )
                VALUES (:transaction_id, 500)
                """
            ),
            {"transaction_id": transaction_id},
        )

    monkeypatch.setattr(barrels_api.db, "engine", v3_engine)

    plan = barrels_api.get_wholesale_purchase_plan(
        [
            Barrel(
                sku="SMALL_RED_BARREL",
                ml_per_barrel=1000,
                potion_type=[1.0, 0, 0, 0],
                price=100,
                quantity=5,
            )
        ]
    )

    assert plan == [BarrelOrder(sku="SMALL_RED_BARREL", quantity=1)]
