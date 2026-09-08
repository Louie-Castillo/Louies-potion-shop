from typing import List

from src.api.bottler import PotionInventory, create_bottle_plan


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
