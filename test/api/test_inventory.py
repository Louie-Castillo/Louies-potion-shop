import pytest
import sqlalchemy
from fastapi import HTTPException, status
from sqlalchemy.engine import Engine

from src import ledger
from src.api import admin, inventory


def seed_inventory_for_reset(engine: Engine) -> None:
    with engine.begin() as connection:
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
                VALUES
                    (1, 'RED_POTION_0', 'red potion', 999, 50, 100, 0, 0, 0),
                    (2, 'GREEN_POTION_0', 'green potion', 999, 50, 0, 100, 0, 0)
                """
            )
        )
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO carts (
                    id,
                    customer_id,
                    customer_name,
                    character_class,
                    character_species,
                    level,
                    payment,
                    checked_out
                )
                VALUES
                    (1, 'customer-1', 'Buyer', 'Wizard', 'Human', 5, 'gold', TRUE),
                    (2, 'customer-2', 'Browser', 'Fighter', 'Elf', 4, NULL, FALSE)
                """
            )
        )
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO cart_items (id, cart_id, potion_id, quantity)
                VALUES
                    (1, 1, 1, 2),
                    (2, 2, 2, 1)
                """
            )
        )
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE game_time
                SET day = 'Friday', hour = 20
                WHERE id = 1
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
                VALUES ('opening_balance', 'Test opening balance')
                RETURNING id
                """
            )
        ).scalar_one()
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO gold_ledger_entries (transaction_id, change)
                VALUES (:transaction_id, 130)
                """
            ),
            {"transaction_id": opening_transaction_id},
        )
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO ingredient_ledger_entries (
                    transaction_id,
                    ingredient_type,
                    change
                )
                VALUES
                    (:transaction_id, 'red', 100),
                    (:transaction_id, 'green', 200),
                    (:transaction_id, 'blue', 300)
                """
            ),
            {"transaction_id": opening_transaction_id},
        )
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO potion_ledger_entries (
                    transaction_id,
                    potion_id,
                    change
                )
                VALUES
                    (:transaction_id, 1, 4),
                    (:transaction_id, 2, 3)
                """
            ),
            {"transaction_id": opening_transaction_id},
        )
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO capacity_ledger_entries (
                    transaction_id,
                    potion_capacity_change,
                    ml_capacity_change
                )
                VALUES (:transaction_id, 1, 1)
                """
            ),
            {"transaction_id": opening_transaction_id},
        )

        checkout_transaction_id = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO inventory_transactions (
                    transaction_type,
                    cart_id,
                    description,
                    game_day,
                    game_hour
                )
                VALUES (
                    'checkout',
                    1,
                    'Historical checkout',
                    'Thursday',
                    12
                )
                RETURNING id
                """
            )
        ).scalar_one()
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO gold_ledger_entries (transaction_id, change)
                VALUES (:transaction_id, 120)
                """
            ),
            {"transaction_id": checkout_transaction_id},
        )
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO processed_requests (
                    operation_type,
                    request_id,
                    transaction_id,
                    response_status,
                    response_body
                )
                VALUES (
                    'checkout',
                    '1',
                    :transaction_id,
                    200,
                    '{"total_potions_bought": 2, "total_gold_paid": 120}'
                )
                """
            ),
            {"transaction_id": checkout_transaction_id},
        )
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO potion_ledger_entries (
                    transaction_id,
                    potion_id,
                    change
                )
                VALUES (:transaction_id, 1, -2)
                """
            ),
            {"transaction_id": checkout_transaction_id},
        )


def test_audit_and_reset_use_ledgers_idempotently(
    monkeypatch: pytest.MonkeyPatch,
    v3_engine: Engine,
) -> None:
    seed_inventory_for_reset(v3_engine)
    monkeypatch.setattr(inventory.db, "engine", v3_engine)
    monkeypatch.setattr(admin.db, "engine", v3_engine)

    audit_before_reset = inventory.get_inventory()

    assert audit_before_reset.number_of_potions == 5
    assert audit_before_reset.ml_in_barrels == 600
    assert audit_before_reset.gold == 250

    admin.reset()
    admin.reset()

    audit_after_reset = inventory.get_inventory()

    assert audit_after_reset.number_of_potions == 0
    assert audit_after_reset.ml_in_barrels == 0
    assert audit_after_reset.gold == 100

    with v3_engine.begin() as connection:
        reset_transaction_count = connection.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*)
                FROM inventory_transactions
                WHERE transaction_type = 'reset'
                """
            )
        ).scalar_one()
        remaining_carts = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, checked_out
                FROM carts
                ORDER BY id
                """
            )
        ).all()
        remaining_cart_items = connection.execute(
            sqlalchemy.text(
                """
                SELECT cart_id, potion_id, quantity
                FROM cart_items
                ORDER BY id
                """
            )
        ).all()
        game_time = connection.execute(
            sqlalchemy.text(
                """
                SELECT day, hour
                FROM game_time
                WHERE id = 1
                """
            )
        ).one()
        stale_potion_total = connection.execute(
            sqlalchemy.text(
                """
                SELECT SUM(quantity)
                FROM potions
                """
            )
        ).scalar_one()
        historical_checkout_count = connection.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*)
                FROM inventory_transactions
                WHERE
                    transaction_type = 'checkout'
                    AND cart_id = 1
                    AND game_day = 'Thursday'
                    AND game_hour = 12
                """
            )
        ).scalar_one()
        processed_request_count = connection.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*)
                FROM processed_requests
                """
            )
        ).scalar_one()
        capacity = ledger.get_capacity_balances(connection)

    assert reset_transaction_count == 1
    assert len(remaining_carts) == 1
    assert remaining_carts[0].id == 1
    assert bool(remaining_carts[0].checked_out) is True
    assert len(remaining_cart_items) == 1
    assert remaining_cart_items[0].cart_id == 1
    assert remaining_cart_items[0].potion_id == 1
    assert remaining_cart_items[0].quantity == 2
    assert game_time.day is None
    assert game_time.hour is None
    assert stale_potion_total == 1998
    assert historical_checkout_count == 1
    assert processed_request_count == 0
    assert capacity.potion_units == 1
    assert capacity.ml_units == 1


def test_capacity_plan_purchases_and_delivers_upgrade_idempotently(
    monkeypatch: pytest.MonkeyPatch,
    v3_engine: Engine,
) -> None:
    with v3_engine.begin() as connection:
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO potions (
                    id, sku, name, quantity, price,
                    red_ml, green_ml, blue_ml, dark_ml
                )
                VALUES (1, 'RED_POTION_0', 'red potion', 0, 50, 100, 0, 0, 0)
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
                VALUES ('opening_balance', 'Capacity test balance')
                RETURNING id
                """
            )
        ).scalar_one()
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO gold_ledger_entries (transaction_id, change)
                VALUES (:transaction_id, 1500)
                """
            ),
            {"transaction_id": transaction_id},
        )
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO potion_ledger_entries (
                    transaction_id,
                    potion_id,
                    change
                )
                VALUES (:transaction_id, 1, 45)
                """
            ),
            {"transaction_id": transaction_id},
        )

    monkeypatch.setattr(inventory.db, "engine", v3_engine)

    plan = inventory.get_capacity_plan()

    assert plan == inventory.CapacityPlan(potion_capacity=1, ml_capacity=0)
    assert inventory.deliver_capacity_plan(plan, order_id=501) is None
    assert inventory.deliver_capacity_plan(plan, order_id=501) is None

    with v3_engine.begin() as connection:
        capacity = ledger.get_capacity_balances(connection)
        gold = ledger.get_current_gold(connection)
        delivery_count = connection.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*)
                FROM inventory_transactions
                WHERE transaction_type = 'capacity_delivery'
                """
            )
        ).scalar_one()

    assert capacity.potion_units == 2
    assert capacity.maximum_potions == 100
    assert gold == 500
    assert delivery_count == 1


def test_capacity_delivery_rejects_purchase_without_enough_gold(
    monkeypatch: pytest.MonkeyPatch,
    v3_engine: Engine,
) -> None:
    monkeypatch.setattr(inventory.db, "engine", v3_engine)

    with pytest.raises(HTTPException) as error:
        inventory.deliver_capacity_plan(
            inventory.CapacityPlan(potion_capacity=1, ml_capacity=0),
            order_id=502,
        )

    assert error.value.status_code == status.HTTP_409_CONFLICT
    assert error.value.detail == "Not enough gold for this capacity purchase"
