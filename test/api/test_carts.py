from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.api import carts


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


def test_create_cart_uses_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    insert_result = MagicMock()
    insert_result.scalar_one.return_value = 42

    connection = _install_mock_engine(
        monkeypatch,
        [insert_result],
    )

    response = carts.create_cart(
        carts.Customer(
            customer_id="customer-1",
            customer_name="Test Adventurer",
            character_class="Wizard",
            character_species="Human",
            level=5,
        )
    )

    assert response.cart_id == 42

    insert_call = connection.execute.call_args_list[0]
    insert_sql = str(insert_call.args[0])
    insert_parameters = insert_call.args[1][0]

    assert "INSERT INTO carts" in insert_sql
    assert insert_parameters["customer_id"] == "customer-1"
    assert insert_parameters["customer_name"] == "Test Adventurer"


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


def test_checkout_uses_database_price_for_mixed_potion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cart_result = MagicMock()
    cart_result.one_or_none.return_value = SimpleNamespace(
        id=42,
        checked_out=False,
    )

    items_result = MagicMock()
    items_result.all.return_value = [
        SimpleNamespace(
            potion_id=4,
            sku="YELLOW_POTION_0",
            price=60,
            available_quantity=3,
            requested_quantity=2,
        )
    ]

    connection = _install_mock_engine(
        monkeypatch,
        [
            cart_result,
            items_result,
            MagicMock(),
            MagicMock(),
            MagicMock(),
        ],
    )

    response = carts.checkout(
        cart_id=42,
        cart_checkout=carts.CartCheckout(payment="gold"),
    )

    assert response.total_potions_bought == 2
    assert response.total_gold_paid == 120

    potion_update_call = connection.execute.call_args_list[2]
    potion_update_sql = str(potion_update_call.args[0])
    potion_update_parameters = potion_update_call.args[1]

    assert "UPDATE potions" in potion_update_sql
    assert potion_update_parameters == [
        {
            "quantity": 2,
            "potion_id": 4,
        }
    ]

    gold_update_call = connection.execute.call_args_list[3]
    gold_update_parameters = gold_update_call.args[1]

    assert gold_update_parameters["total_gold_paid"] == 120
