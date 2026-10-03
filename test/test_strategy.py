import pytest

from src.strategy import allocate_inventory_targets


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


def test_allocate_inventory_targets_rejects_negative_capacity() -> None:
    with pytest.raises(ValueError, match="capacity must be non-negative"):
        allocate_inventory_targets([1], {}, capacity=-1)
