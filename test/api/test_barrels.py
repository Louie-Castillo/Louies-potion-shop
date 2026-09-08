from src.api.barrels import (
    calculate_barrel_summary,
    create_barrel_plan,
    Barrel,
    BarrelOrder,
)
from typing import List


def test_barrel_delivery() -> None:
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
