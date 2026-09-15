from typing import List

import pytest
import sqlalchemy
from fastapi import HTTPException, status
from sqlalchemy.engine import Engine

from src.api import bottler
from src.api.bottler import PotionInventory, PotionMixes, create_bottle_plan


def seed_bottler_inventory(
    engine: Engine,
    red_ml: int,
    green_ml: int,
    potion_quantity: int = 0,
) -> None:
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
                VALUES (
                    1,
                    'YELLOW_POTION_0',
                    'yellow potion',
                    999,
                    60,
                    50,
                    50,
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
                VALUES (
                    'opening_balance',
                    'Test opening balance'
                )
                RETURNING id
                """
            )
        ).scalar_one()
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO ingredient_ledger_entries (
                    transaction_id,
                    ingredient_type,
                    change
                )
                VALUES
                    (:transaction_id, 'red', :red_ml),
                    (:transaction_id, 'green', :green_ml)
                """
            ),
            {
                "transaction_id": transaction_id,
                "red_ml": red_ml,
                "green_ml": green_ml,
            },
        )

        if potion_quantity != 0:
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
                        1,
                        :change
                    )
                    """
                ),
                {
                    "transaction_id": transaction_id,
                    "change": potion_quantity,
                },
            )


def test_bottle_red_potions() -> None:
    red_ml: int = 100
    green_ml: int = 0
    blue_ml: int = 0
    dark_ml: int = 0
    maximum_potion_capacity: int = 1000
    current_potion_inventory: List[PotionInventory] = [
        PotionInventory(
            potion_type=[100, 0, 0, 0],
            quantity=0,
        )
    ]

    result = create_bottle_plan(
        red_ml=red_ml,
        green_ml=green_ml,
        blue_ml=blue_ml,
        dark_ml=dark_ml,
        maximum_potion_capacity=maximum_potion_capacity,
        current_potion_inventory=current_potion_inventory,
    )

    assert len(result) == 1
    assert result[0].potion_type == [100, 0, 0, 0]
    assert result[0].quantity == 1


def test_bottle_mixed_potions() -> None:
    current_potion_inventory: List[PotionInventory] = [
        PotionInventory(
            potion_type=[50, 50, 0, 0],
            quantity=0,
        )
    ]

    result = create_bottle_plan(
        red_ml=100,
        green_ml=100,
        blue_ml=0,
        dark_ml=0,
        maximum_potion_capacity=50,
        current_potion_inventory=current_potion_inventory,
    )

    assert len(result) == 1
    assert result[0].potion_type == [50, 50, 0, 0]
    assert result[0].quantity == 2


def test_bottle_delivery_writes_ledgers_only_once(
    monkeypatch: pytest.MonkeyPatch,
    v3_engine: Engine,
) -> None:
    seed_bottler_inventory(v3_engine, red_ml=500, green_ml=500)
    monkeypatch.setattr(bottler.db, "engine", v3_engine)

    delivery = [PotionMixes(potion_type=[50, 50, 0, 0], quantity=2)]

    assert bottler.post_deliver_bottles(delivery, order_id=101) is None
    assert bottler.post_deliver_bottles(delivery, order_id=101) is None

    with v3_engine.begin() as connection:
        ingredient_balances = connection.execute(
            sqlalchemy.text(
                """
                SELECT ingredient_type, SUM(change) AS balance
                FROM ingredient_ledger_entries
                GROUP BY ingredient_type
                ORDER BY ingredient_type
                """
            )
        ).all()
        potion_balance = connection.execute(
            sqlalchemy.text(
                """
                SELECT COALESCE(SUM(change), 0)
                FROM potion_ledger_entries
                WHERE potion_id = 1
                """
            )
        ).scalar_one()
        delivery_transaction_count = connection.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*)
                FROM inventory_transactions
                WHERE transaction_type = 'bottle_delivery'
                """
            )
        ).scalar_one()
        stale_quantity = connection.execute(
            sqlalchemy.text(
                """
                SELECT quantity
                FROM potions
                WHERE id = 1
                """
            )
        ).scalar_one()

    assert {row.ingredient_type: row.balance for row in ingredient_balances} == {
        "green": 400,
        "red": 400,
    }
    assert potion_balance == 2
    assert delivery_transaction_count == 1
    assert stale_quantity == 999


def test_bottle_delivery_retry_returns_stored_ingredient_error(
    monkeypatch: pytest.MonkeyPatch,
    v3_engine: Engine,
) -> None:
    seed_bottler_inventory(v3_engine, red_ml=40, green_ml=40)
    monkeypatch.setattr(bottler.db, "engine", v3_engine)
    delivery = [PotionMixes(potion_type=[50, 50, 0, 0], quantity=1)]

    with pytest.raises(HTTPException) as first_error:
        bottler.post_deliver_bottles(delivery, order_id=102)

    with v3_engine.begin() as connection:
        credit_transaction_id = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO inventory_transactions (
                    transaction_type,
                    description
                )
                VALUES ('test_credit', 'Add ingredients after failure')
                RETURNING id
                """
            )
        ).scalar_one()
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
                    (:transaction_id, 'green', 100)
                """
            ),
            {"transaction_id": credit_transaction_id},
        )

    with pytest.raises(HTTPException) as retry_error:
        bottler.post_deliver_bottles(delivery, order_id=102)

    assert first_error.value.status_code == status.HTTP_409_CONFLICT
    assert retry_error.value.status_code == first_error.value.status_code
    assert retry_error.value.detail == first_error.value.detail

    with v3_engine.begin() as connection:
        delivery_transaction_count = connection.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*)
                FROM inventory_transactions
                WHERE transaction_type = 'bottle_delivery'
                """
            )
        ).scalar_one()

    assert delivery_transaction_count == 0


def test_bottle_delivery_rejects_unconfigured_recipe(
    monkeypatch: pytest.MonkeyPatch,
    v3_engine: Engine,
) -> None:
    seed_bottler_inventory(v3_engine, red_ml=500, green_ml=500)
    monkeypatch.setattr(bottler.db, "engine", v3_engine)

    with pytest.raises(HTTPException) as error:
        bottler.post_deliver_bottles(
            [PotionMixes(potion_type=[100, 0, 0, 0], quantity=1)],
            order_id=103,
        )

    assert error.value.status_code == status.HTTP_400_BAD_REQUEST
    assert error.value.detail == "Delivered potion recipe is not configured"


def test_bottle_delivery_enforces_potion_capacity(
    monkeypatch: pytest.MonkeyPatch,
    v3_engine: Engine,
) -> None:
    seed_bottler_inventory(
        v3_engine,
        red_ml=500,
        green_ml=500,
        potion_quantity=50,
    )
    monkeypatch.setattr(bottler.db, "engine", v3_engine)

    with pytest.raises(HTTPException) as error:
        bottler.post_deliver_bottles(
            [PotionMixes(potion_type=[50, 50, 0, 0], quantity=1)],
            order_id=104,
        )

    assert error.value.status_code == status.HTTP_409_CONFLICT
    assert error.value.detail == "Not enough potion capacity for this delivery"


def test_bottle_plan_reads_ledger_balances(
    monkeypatch: pytest.MonkeyPatch,
    v3_engine: Engine,
) -> None:
    seed_bottler_inventory(v3_engine, red_ml=500, green_ml=500)
    monkeypatch.setattr(bottler.db, "engine", v3_engine)

    plan = bottler.get_bottle_plan()

    assert len(plan) == 1
    assert plan[0].potion_type == [50, 50, 0, 0]
    assert plan[0].quantity == 10
