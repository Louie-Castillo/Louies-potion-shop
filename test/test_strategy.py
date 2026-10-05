import pytest

from src.strategy import (
    allocate_inventory_targets,
    build_market_minimum_targets,
    estimate_potion_margins,
)


def test_allocate_inventory_targets_follows_recorded_demand() -> None:
    targets = allocate_inventory_targets(
        potion_ids=[1, 2, 3, 4],
        units_sold={1: 132, 2: 14, 3: 7, 4: 14},
        capacity=50,
    )

    assert targets == {1: 40, 2: 4, 3: 2, 4: 4}


def test_allocate_inventory_targets_uses_safe_fallback_without_sales() -> None:
    targets = allocate_inventory_targets(
        potion_ids=[1, 2, 3, 4],
        units_sold={},
        capacity=50,
    )

    assert targets == {1: 13, 2: 13, 3: 12, 4: 12}


def test_allocate_inventory_targets_reserves_exploration_stock() -> None:
    targets = allocate_inventory_targets(
        potion_ids=[1, 2, 3, 4, 5, 6],
        units_sold={1: 132, 2: 14, 3: 7, 4: 14},
        capacity=50,
    )

    assert targets == {1: 38, 2: 4, 3: 2, 4: 4, 5: 1, 6: 1}


def test_estimate_potion_margins_uses_observed_ingredient_costs() -> None:
    margins = estimate_potion_margins(
        potion_specs={
            1: (50, [100, 0, 0, 0]),
            2: (60, [50, 50, 0, 0]),
        },
        ingredient_costs={"red": 0.1, "green": 0.2},
    )

    assert margins == {1: 40.0, 2: 45.0}


def test_allocate_inventory_targets_rejects_negative_capacity() -> None:
    with pytest.raises(ValueError, match="capacity must be non-negative"):
        allocate_inventory_targets([1], {}, capacity=-1)


def test_dark_market_reserves_larger_night_inventory() -> None:
    recipes = {
        1: [100, 0, 0, 0],
        2: [0, 100, 0, 0],
        3: [0, 0, 100, 0],
        4: [50, 50, 0, 0],
        5: [50, 0, 50, 0],
        7: [0, 0, 0, 100],
    }

    day_targets = build_market_minimum_targets(recipes, capacity=50, game_hour=10)
    night_targets = build_market_minimum_targets(recipes, capacity=50, game_hour=20)

    assert day_targets[7] == 10
    assert night_targets[7] == 20
    assert all(day_targets[potion_id] == 3 for potion_id in (1, 2, 3, 4, 5))
    assert all(night_targets[potion_id] == 3 for potion_id in (1, 2, 3, 4, 5))


def test_minimum_targets_preserve_dark_stock_before_demand_weighting() -> None:
    targets = allocate_inventory_targets(
        potion_ids=[1, 2, 3, 4, 5, 7],
        units_sold={1: 236},
        capacity=50,
        minimum_targets={1: 3, 2: 3, 3: 3, 4: 3, 5: 3, 7: 20},
    )

    assert targets == {1: 18, 2: 3, 3: 3, 4: 3, 5: 3, 7: 20}


def test_market_minimum_targets_reject_negative_capacity() -> None:
    with pytest.raises(ValueError, match="capacity must be non-negative"):
        build_market_minimum_targets({1: [100, 0, 0, 0]}, -1, 20)
