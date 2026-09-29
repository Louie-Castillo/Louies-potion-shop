from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sqlalchemy
from fastapi import HTTPException, status
from sqlalchemy.engine import Engine

from src.api import carts


def seed_search_orders(engine: Engine) -> None:
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
                    (1, 'RED_POTION_0', 'red potion', 0, 50, 100, 0, 0, 0),
                    (2, 'YELLOW_POTION_0', 'yellow potion', 0, 60, 50, 50, 0, 0)
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
                    checked_out,
                    checked_out_at
                )
                VALUES
                    (
                        10,
                        'customer-10',
                        'Ada',
                        'Warrior',
                        'Folk',
                        8,
                        TRUE,
                        '2026-09-01 08:00:00'
                    ),
                    (
                        11,
                        'customer-11',
                        'Bram',
                        'Hunter',
                        'Dvergar',
                        12,
                        TRUE,
                        '2026-09-01 10:00:00'
                    ),
                    (
                        12,
                        'customer-12',
                        'Cara',
                        'Seer',
                        'Alfar',
                        5,
                        FALSE,
                        NULL
                    )
                """
            )
        )
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO cart_items (
                    id,
                    cart_id,
                    potion_id,
                    quantity
                )
                VALUES
                    (100, 10, 1, 2),
                    (101, 10, 2, 1),
                    (102, 11, 2, 3),
                    (103, 12, 1, 9)
                """
            )
        )


def seed_checkout(
    engine: Engine,
    available_quantity: int,
    requested_quantity: int = 2,
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
                    4,
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
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO carts (
                    id,
                    customer_id,
                    customer_name,
                    character_class,
                    character_species,
                    level
                )
                VALUES (
                    42,
                    'customer-1',
                    'Test Adventurer',
                    'Wizard',
                    'Human',
                    5
                )
                """
            )
        )
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO cart_items (
                    cart_id,
                    potion_id,
                    quantity
                )
                VALUES (
                    42,
                    4,
                    :requested_quantity
                )
                """
            ),
            {"requested_quantity": requested_quantity},
        )
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE game_time
                SET day = 'Monday', hour = 14
                WHERE id = 1
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
                VALUES (:transaction_id, 100)
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
                VALUES (
                    :transaction_id,
                    4,
                    :available_quantity
                )
                """
            ),
            {
                "transaction_id": transaction_id,
                "available_quantity": available_quantity,
            },
        )


def _install_mock_engine(
    monkeypatch: pytest.MonkeyPatch,
    results: list[MagicMock],
) -> MagicMock:
    connection = MagicMock()
    connection.execute.side_effect = results

    transaction = MagicMock()
    transaction.__enter__.return_value = connection
    transaction.__exit__.return_value = False

    engine = MagicMock()
    engine.begin.return_value = transaction

    monkeypatch.setattr(carts.db, "engine", engine)

    return connection


def test_search_orders_returns_real_completed_line_items(
    monkeypatch: pytest.MonkeyPatch,
    v3_engine: Engine,
) -> None:
    seed_search_orders(v3_engine)
    monkeypatch.setattr(carts.db, "engine", v3_engine)

    response = carts.search_orders()

    assert response.previous is None
    assert response.next is None
    assert [item.line_item_id for item in response.results] == [102, 101, 100]
    assert response.results[0] == carts.LineItem(
        line_item_id=102,
        item_sku="YELLOW_POTION_0",
        customer_name="Bram",
        line_item_total=180,
        timestamp="2026-09-01T10:00:00Z",
    )
    assert response.results[1] == carts.LineItem(
        line_item_id=101,
        item_sku="YELLOW_POTION_0",
        customer_name="Ada",
        line_item_total=60,
        timestamp="2026-09-01T08:00:00Z",
    )
    assert response.results[2].line_item_total == 100
    assert 103 not in {item.line_item_id for item in response.results}


def test_search_orders_returns_empty_results_when_no_orders_exist(
    monkeypatch: pytest.MonkeyPatch,
    v3_engine: Engine,
) -> None:
    monkeypatch.setattr(carts.db, "engine", v3_engine)

    response = carts.search_orders()

    assert response == carts.SearchResponse(
        previous=None,
        next=None,
        results=[],
    )


@pytest.mark.parametrize(
    ("customer_name", "potion_sku", "expected_line_item_ids"),
    [
        ("ad", "", [101, 100]),
        ("ADA", "", [101, 100]),
        ("", "yellow", [102, 101]),
        ("", "YELLOW_POTION", [102, 101]),
        ("ada", "red", [100]),
        ("bram", "red", []),
        ("nobody", "", []),
        ("   ", "   ", [102, 101, 100]),
    ],
)
def test_search_orders_filters_by_customer_and_potion_sku(
    monkeypatch: pytest.MonkeyPatch,
    v3_engine: Engine,
    customer_name: str,
    potion_sku: str,
    expected_line_item_ids: list[int],
) -> None:
    seed_search_orders(v3_engine)
    monkeypatch.setattr(carts.db, "engine", v3_engine)

    response = carts.search_orders(
        customer_name=customer_name,
        potion_sku=potion_sku,
    )

    assert [item.line_item_id for item in response.results] == expected_line_item_ids
    assert response.previous is None
    assert response.next is None


def test_create_cart_reuses_open_cart_but_not_checked_out_cart(
    monkeypatch: pytest.MonkeyPatch,
    v3_engine: Engine,
) -> None:
    monkeypatch.setattr(carts.db, "engine", v3_engine)
    customer = carts.Customer(
        customer_id="customer-1",
        customer_name="Test Adventurer",
        character_class="Wizard",
        character_species="Human",
        level=5,
    )

    response = carts.create_cart(customer)
    retry_response = carts.create_cart(customer)

    assert retry_response == response

    with v3_engine.begin() as connection:
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE carts
                SET checked_out = TRUE
                WHERE id = :cart_id
                """
            ),
            {"cart_id": response.cart_id},
        )

    next_visit_response = carts.create_cart(customer)

    assert next_visit_response.cart_id != response.cart_id

    with v3_engine.begin() as connection:
        carts_created = connection.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*)
                FROM carts
                WHERE customer_id = 'customer-1'
                """
            )
        ).scalar_one()
        open_cart_id = connection.execute(
            sqlalchemy.text(
                """
                SELECT id
                FROM carts
                WHERE
                    customer_id = 'customer-1'
                    AND checked_out = FALSE
                """
            )
        ).scalar_one()

    assert carts_created == 2
    assert open_cart_id == next_visit_response.cart_id


def test_add_mixed_potion_to_cart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cart_result = MagicMock()
    cart_result.one_or_none.return_value = SimpleNamespace(
        id=42,
        checked_out=False,
    )

    potion_result = MagicMock()
    potion_result.scalar_one_or_none.return_value = 4

    upsert_result = MagicMock()

    connection = _install_mock_engine(
        monkeypatch,
        [
            cart_result,
            potion_result,
            upsert_result,
        ],
    )

    response = carts.set_item_quantity(
        cart_id=42,
        item_sku="YELLOW_POTION_0",
        cart_item=carts.CartItem(quantity=2),
    )

    assert response is None

    upsert_call = connection.execute.call_args_list[2]
    upsert_sql = str(upsert_call.args[0])
    upsert_parameters = upsert_call.args[1]

    assert "INSERT INTO cart_items" in upsert_sql
    assert "ON CONFLICT" in upsert_sql
    assert upsert_parameters["cart_id"] == 42
    assert upsert_parameters["potion_id"] == 4
    assert upsert_parameters["quantity"] == 2


def test_checkout_writes_ledgers_and_sale_instrumentation_once(
    monkeypatch: pytest.MonkeyPatch,
    v3_engine: Engine,
) -> None:
    seed_checkout(v3_engine, available_quantity=3)
    monkeypatch.setattr(carts.db, "engine", v3_engine)

    response = carts.checkout(
        cart_id=42,
        cart_checkout=carts.CartCheckout(payment="gold"),
    )
    retry_response = carts.checkout(
        cart_id=42,
        cart_checkout=carts.CartCheckout(payment="gold"),
    )

    assert response.total_potions_bought == 2
    assert response.total_gold_paid == 120
    assert retry_response == response

    with v3_engine.begin() as connection:
        gold_balance = connection.execute(
            sqlalchemy.text(
                """
                SELECT SUM(change)
                FROM gold_ledger_entries
                """
            )
        ).scalar_one()
        potion_balance = connection.execute(
            sqlalchemy.text(
                """
                SELECT SUM(change)
                FROM potion_ledger_entries
                WHERE potion_id = 4
                """
            )
        ).scalar_one()
        sale = connection.execute(
            sqlalchemy.text(
                """
                SELECT
                    it.game_day,
                    it.game_hour,
                    c.customer_name,
                    c.character_class,
                    c.character_species,
                    c.level,
                    p.sku,
                    -ple.change AS quantity_sold
                FROM inventory_transactions AS it
                JOIN carts AS c
                    ON c.id = it.cart_id
                JOIN potion_ledger_entries AS ple
                    ON ple.transaction_id = it.id
                JOIN potions AS p
                    ON p.id = ple.potion_id
                WHERE it.transaction_type = 'checkout'
                """
            )
        ).one()
        checkout_count = connection.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*)
                FROM inventory_transactions
                WHERE transaction_type = 'checkout'
                """
            )
        ).scalar_one()
        cart = connection.execute(
            sqlalchemy.text(
                """
                SELECT checked_out, payment
                FROM carts
                WHERE id = 42
                """
            )
        ).one()
        stale_quantity = connection.execute(
            sqlalchemy.text(
                """
                SELECT quantity
                FROM potions
                WHERE id = 4
                """
            )
        ).scalar_one()

    assert gold_balance == 220
    assert potion_balance == 1
    assert checkout_count == 1
    assert bool(cart.checked_out) is True
    assert cart.payment == "gold"
    assert stale_quantity == 999
    assert sale.game_day == "Monday"
    assert sale.game_hour == 14
    assert sale.customer_name == "Test Adventurer"
    assert sale.character_class == "Wizard"
    assert sale.character_species == "Human"
    assert sale.level == 5
    assert sale.sku == "YELLOW_POTION_0"
    assert sale.quantity_sold == 2


def test_checkout_retry_returns_stored_inventory_error(
    monkeypatch: pytest.MonkeyPatch,
    v3_engine: Engine,
) -> None:
    seed_checkout(v3_engine, available_quantity=1)
    monkeypatch.setattr(carts.db, "engine", v3_engine)

    with pytest.raises(HTTPException) as first_error:
        carts.checkout(
            cart_id=42,
            cart_checkout=carts.CartCheckout(payment="gold"),
        )

    with v3_engine.begin() as connection:
        restock_transaction_id = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO inventory_transactions (
                    transaction_type,
                    description
                )
                VALUES ('test_restock', 'Restock after checkout failure')
                RETURNING id
                """
            )
        ).scalar_one()
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO potion_ledger_entries (
                    transaction_id,
                    potion_id,
                    change
                )
                VALUES (:transaction_id, 4, 10)
                """
            ),
            {"transaction_id": restock_transaction_id},
        )

    with pytest.raises(HTTPException) as retry_error:
        carts.checkout(
            cart_id=42,
            cart_checkout=carts.CartCheckout(payment="gold"),
        )

    assert first_error.value.status_code == status.HTTP_409_CONFLICT
    assert retry_error.value.status_code == first_error.value.status_code
    assert retry_error.value.detail == first_error.value.detail

    with v3_engine.begin() as connection:
        checkout_count = connection.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*)
                FROM inventory_transactions
                WHERE transaction_type = 'checkout'
                """
            )
        ).scalar_one()
        checked_out = connection.execute(
            sqlalchemy.text(
                """
                SELECT checked_out
                FROM carts
                WHERE id = 42
                """
            )
        ).scalar_one()

    assert checkout_count == 0
    assert bool(checked_out) is False
