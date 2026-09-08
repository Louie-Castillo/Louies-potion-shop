from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from typing import List
from src.api import auth
import sqlalchemy
from src import database as db

router = APIRouter(
    prefix="/bottler",
    tags=["bottler"],
    dependencies=[Depends(auth.get_api_key)],
)


class PotionMixes(BaseModel):
    potion_type: List[int] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Must contain exactly 4 elements: [r, g, b, d]",
    )
    quantity: int = Field(
        ..., ge=1, le=10000, description="Quantity must be between 1 and 10,000"
    )

    @field_validator("potion_type")
    @classmethod
    def validate_potion_type(cls, potion_type: List[int]) -> List[int]:
        if sum(potion_type) != 100:
            raise ValueError("Sum of potion_type values must be exactly 100")
        return potion_type


class PotionInventory(BaseModel):
    potion_type: List[int] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Must contain exactly 4 elements: [r, g, b, d]",
    )
    quantity: int = Field(ge=0)

    @field_validator("potion_type")
    @classmethod
    def validate_potion_type(cls, potion_type: List[int]) -> List[int]:
        if sum(potion_type) != 100:
            raise ValueError("Sum of potion_type values must be exactly 100")
        return potion_type


@router.post("/deliver/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def post_deliver_bottles(
    potions_delivered: List[PotionMixes],
    order_id: int,
) -> None:
    """
    Records delivered potions and subtracts the raw ingredients used.
    """
    print(f"potions delivered: {potions_delivered} order_id: {order_id}")

    ingredients_used = [0, 0, 0, 0]

    for potion in potions_delivered:
        for index, amount in enumerate(potion.potion_type):
            ingredients_used[index] += amount * potion.quantity

    with db.engine.begin() as connection:
        raw_inventory = connection.execute(
            sqlalchemy.text(
                """
                SELECT red_ml, green_ml, blue_ml
                FROM global_inventory
                WHERE id = 1
                FOR UPDATE
                """
            )
        ).one()

        available_ml = [
            raw_inventory.red_ml,
            raw_inventory.green_ml,
            raw_inventory.blue_ml,
            0,
        ]

        if any(
            amount_used > amount_available
            for amount_used, amount_available in zip(
                ingredients_used,
                available_ml,
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Not enough raw ingredients for this delivery",
            )

        for potion in potions_delivered:
            red_ml, green_ml, blue_ml, dark_ml = potion.potion_type

            potion_id = connection.execute(
                sqlalchemy.text(
                    """
                    UPDATE potions
                    SET quantity = quantity + :quantity
                    WHERE
                        red_ml = :red_ml
                        AND green_ml = :green_ml
                        AND blue_ml = :blue_ml
                        AND dark_ml = :dark_ml
                    RETURNING id
                    """
                ),
                {
                    "quantity": potion.quantity,
                    "red_ml": red_ml,
                    "green_ml": green_ml,
                    "blue_ml": blue_ml,
                    "dark_ml": dark_ml,
                },
            ).scalar_one_or_none()

            if potion_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Delivered potion recipe is not configured",
                )

        connection.execute(
            sqlalchemy.text(
                """
                UPDATE global_inventory
                SET
                    red_ml = red_ml - :red_ml_used,
                    green_ml = green_ml - :green_ml_used,
                    blue_ml = blue_ml - :blue_ml_used
                WHERE id = 1
                """
            ),
            {
                "red_ml_used": ingredients_used[0],
                "green_ml_used": ingredients_used[1],
                "blue_ml_used": ingredients_used[2],
            },
        )


def create_bottle_plan(
    red_ml: int,
    green_ml: int,
    blue_ml: int,
    dark_ml: int,
    maximum_potion_capacity: int,
    current_potion_inventory: List[PotionInventory],
) -> List[PotionMixes]:
    available_ml = [red_ml, green_ml, blue_ml, dark_ml]

    current_quantity = sum(potion.quantity for potion in current_potion_inventory)
    remaining_capacity = max(
        0,
        maximum_potion_capacity - current_quantity,
    )

    plan: List[PotionMixes] = []

    for potion in current_potion_inventory:
        if remaining_capacity == 0:
            break

        recipe = potion.potion_type

        ingredient_limits = [
            available_ml[index] // amount
            for index, amount in enumerate(recipe)
            if amount > 0
        ]

        if not ingredient_limits:
            continue

        quantity_to_make = min(
            remaining_capacity,
            min(ingredient_limits),
        )

        if quantity_to_make == 0:
            continue

        plan.append(
            PotionMixes(
                potion_type=recipe,
                quantity=quantity_to_make,
            )
        )

        for index, amount in enumerate(recipe):
            available_ml[index] -= amount * quantity_to_make

        remaining_capacity -= quantity_to_make

    return plan


@router.post("/plan", response_model=List[PotionMixes])
def get_bottle_plan():
    """
    Gets the plan for bottling potions.
    Each bottle has a quantity of what proportion of red, green, blue, and dark potions to add.
    Colors are expressed in integers from 0 to 100 that must sum up to exactly 100.
    """
    with db.engine.begin() as connection:
        raw_inventory = connection.execute(
            sqlalchemy.text(
                """
                SELECT red_ml, green_ml, blue_ml
                FROM global_inventory
                WHERE id = 1
                """
            )
        ).one()

        potion_rows = connection.execute(
            sqlalchemy.text(
                """
                SELECT
                    red_ml,
                    green_ml,
                    blue_ml,
                    dark_ml,
                    quantity
                FROM potions
                ORDER BY
                    (
                        CASE WHEN red_ml > 0 THEN 1 ELSE 0 END +
                        CASE WHEN green_ml > 0 THEN 1 ELSE 0 END +
                        CASE WHEN blue_ml > 0 THEN 1 ELSE 0 END +
                        CASE WHEN dark_ml > 0 THEN 1 ELSE 0 END
                    ) DESC,
                    id
                """
            )
        ).all()

    potion_inventory = [
        PotionInventory(
            potion_type=[
                row.red_ml,
                row.green_ml,
                row.blue_ml,
                row.dark_ml,
            ],
            quantity=row.quantity,
        )
        for row in potion_rows
    ]

    return create_bottle_plan(
        red_ml=raw_inventory.red_ml,
        green_ml=raw_inventory.green_ml,
        blue_ml=raw_inventory.blue_ml,
        dark_ml=0,
        maximum_potion_capacity=50,
        current_potion_inventory=potion_inventory,
    )


if __name__ == "__main__":
    print(get_bottle_plan())
