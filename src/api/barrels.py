from dataclasses import dataclass
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from typing import List

import sqlalchemy
from src.api import auth
from src import database as db


router = APIRouter(
    prefix="/barrels",
    tags=["barrels"],
    dependencies=[Depends(auth.get_api_key)],
)


class Barrel(BaseModel):
    sku: str
    ml_per_barrel: int = Field(gt=0, description="Must be greater than 0")
    potion_type: List[float] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Must contain exactly 4 elements: [r, g, b, d] that sum to 1.0",
    )
    price: int = Field(ge=0, description="Price must be non-negative")
    quantity: int = Field(ge=0, description="Quantity must be non-negative")

    @field_validator("potion_type")
    @classmethod
    def validate_potion_type(cls, potion_type: List[float]) -> List[float]:
        if len(potion_type) != 4:
            raise ValueError("potion_type must have exactly 4 elements: [r, g, b, d]")
        if not abs(sum(potion_type) - 1.0) < 1e-6:
            raise ValueError("Sum of potion_type values must be exactly 1.0")
        return potion_type


class BarrelOrder(BaseModel):
    sku: str
    quantity: int = Field(gt=0, description="Quantity must be greater than 0")


@dataclass
class BarrelSummary:
    gold_paid: int


def calculate_barrel_summary(barrels: List[Barrel]) -> BarrelSummary:
    return BarrelSummary(gold_paid=sum(b.price * b.quantity for b in barrels))


@router.post("/deliver/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def post_deliver_barrels(
    barrels_delivered: List[Barrel],
    order_id: int,
) -> None:
    """
    Records delivered barrels, subtracts their cost, and adds their ingredients.
    """
    print(f"barrels delivered: {barrels_delivered} order_id: {order_id}")

    delivery = calculate_barrel_summary(barrels_delivered)
    ingredients_delivered = [0, 0, 0, 0]

    for barrel in barrels_delivered:
        total_ml = barrel.ml_per_barrel * barrel.quantity

        for index, proportion in enumerate(barrel.potion_type):
            ingredients_delivered[index] += round(total_ml * proportion)

    if ingredients_delivered[3] > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dark ingredient storage is not currently supported",
        )

    with db.engine.begin() as connection:
        inventory = connection.execute(
            sqlalchemy.text(
                """
                SELECT gold, red_ml, green_ml, blue_ml
                FROM global_inventory
                WHERE id = 1
                FOR UPDATE
                """
            )
        ).one()

        if delivery.gold_paid > inventory.gold:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Not enough gold for this barrel delivery",
            )

        current_ml = inventory.red_ml + inventory.green_ml + inventory.blue_ml
        delivered_ml = sum(ingredients_delivered[:3])

        if current_ml + delivered_ml > 10000:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Not enough capacity for this barrel delivery",
            )

        connection.execute(
            sqlalchemy.text(
                """
                UPDATE global_inventory
                SET
                    gold = gold - :gold_paid,
                    red_ml = red_ml + :red_ml_delivered,
                    green_ml = green_ml + :green_ml_delivered,
                    blue_ml = blue_ml + :blue_ml_delivered
                WHERE id = 1
                """
            ),
            {
                "gold_paid": delivery.gold_paid,
                "red_ml_delivered": ingredients_delivered[0],
                "green_ml_delivered": ingredients_delivered[1],
                "blue_ml_delivered": ingredients_delivered[2],
            },
        )


def create_barrel_plan(
    gold: int,
    max_barrel_capacity: int,
    current_ml: List[int],
    target_potion_type: List[int],
    wholesale_catalog: List[Barrel],
) -> List[BarrelOrder]:
    remaining_capacity = max(
        0,
        max_barrel_capacity - sum(current_ml),
    )

    if gold <= 0 or remaining_capacity == 0:
        return []

    # Dark ingredients cannot be stored in global_inventory yet.
    if target_potion_type[3] > 0:
        return []

    required_ingredients = [
        index for index, amount in enumerate(target_potion_type) if amount > 0
    ]

    if not required_ingredients:
        return []

    # Find the ingredient for which we can currently make the fewest
    # bottles of the selected potion.
    bottleneck_index = min(
        required_ingredients,
        key=lambda index: (current_ml[index] / target_potion_type[index]),
    )

    candidates = [
        barrel
        for barrel in wholesale_catalog
        if barrel.quantity > 0
        and barrel.price <= gold
        and barrel.ml_per_barrel <= remaining_capacity
        and barrel.potion_type[3] == 0
        and barrel.potion_type[bottleneck_index] > 0
    ]

    if not candidates:
        return []

    selected_barrel = min(
        candidates,
        key=lambda barrel: (
            barrel.ml_per_barrel,
            barrel.price,
            barrel.sku,
        ),
    )

    return [
        BarrelOrder(
            sku=selected_barrel.sku,
            quantity=1,
        )
    ]


@router.post("/plan", response_model=List[BarrelOrder])
def get_wholesale_purchase_plan(
    wholesale_catalog: List[Barrel],
) -> List[BarrelOrder]:
    """
    Selects barrels that provide ingredients for a potion recipe
    configured in the potions table.
    """
    print(f"barrel catalog: {wholesale_catalog}")

    with db.engine.begin() as connection:
        inventory = connection.execute(
            sqlalchemy.text(
                """
                SELECT gold, red_ml, green_ml, blue_ml
                FROM global_inventory
                WHERE id = 1
                """
            )
        ).one()

        target_potion = connection.execute(
            sqlalchemy.text(
                """
                SELECT
                    red_ml,
                    green_ml,
                    blue_ml,
                    dark_ml
                FROM potions
                ORDER BY
                    quantity ASC,
                    (
                        CASE WHEN red_ml > 0 THEN 1 ELSE 0 END +
                        CASE WHEN green_ml > 0 THEN 1 ELSE 0 END +
                        CASE WHEN blue_ml > 0 THEN 1 ELSE 0 END +
                        CASE WHEN dark_ml > 0 THEN 1 ELSE 0 END
                    ) DESC,
                    id
                LIMIT 1
                """
            )
        ).one_or_none()

    if target_potion is None:
        return []

    return create_barrel_plan(
        gold=inventory.gold,
        max_barrel_capacity=10000,
        current_ml=[
            inventory.red_ml,
            inventory.green_ml,
            inventory.blue_ml,
            0,
        ],
        target_potion_type=[
            target_potion.red_ml,
            target_potion.green_ml,
            target_potion.blue_ml,
            target_potion.dark_ml,
        ],
        wholesale_catalog=wholesale_catalog,
    )
