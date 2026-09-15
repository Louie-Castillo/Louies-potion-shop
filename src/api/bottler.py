from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from typing import List
from src.api import auth
import sqlalchemy
from src import database as db
from src import idempotency, ledger

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
        if any(amount < 0 or amount > 100 for amount in potion_type):
            raise ValueError("potion_type values must be between 0 and 100")
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
        if any(amount < 0 or amount > 100 for amount in potion_type):
            raise ValueError("potion_type values must be between 0 and 100")
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

    operation_type = "bottle_delivery"
    request_id = str(order_id)
    error_status: int | None = None
    error_detail: str | None = None

    with db.engine.begin() as connection:
        processed_request_id = idempotency.reserve_request(
            connection,
            operation_type,
            request_id,
        )

        if processed_request_id is None:
            stored_response = idempotency.get_stored_response(
                connection,
                operation_type,
                request_id,
            )

            if stored_response.status_code == status.HTTP_204_NO_CONTENT:
                return None

            detail = "Previously processed bottle delivery failed"

            if isinstance(stored_response.body, dict):
                stored_detail = stored_response.body.get("detail")
                if isinstance(stored_detail, str):
                    detail = stored_detail

            raise HTTPException(
                status_code=stored_response.status_code,
                detail=detail,
            )

        lock_query = """
            SELECT id
            FROM global_inventory
            WHERE id = 1
        """

        if connection.dialect.name == "postgresql":
            lock_query += " FOR UPDATE"

        connection.execute(sqlalchemy.text(lock_query)).one()

        potion_quantities_to_add: dict[int, int] = {}

        for potion in potions_delivered:
            red_ml, green_ml, blue_ml, dark_ml = potion.potion_type

            potion_id = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT id
                    FROM potions
                    WHERE
                        red_ml = :red_ml
                        AND green_ml = :green_ml
                        AND blue_ml = :blue_ml
                        AND dark_ml = :dark_ml
                    """
                ),
                {
                    "red_ml": red_ml,
                    "green_ml": green_ml,
                    "blue_ml": blue_ml,
                    "dark_ml": dark_ml,
                },
            ).scalar_one_or_none()

            if potion_id is None:
                error_status = status.HTTP_400_BAD_REQUEST
                error_detail = "Delivered potion recipe is not configured"
                break

            potion_id = int(potion_id)
            potion_quantities_to_add[potion_id] = (
                potion_quantities_to_add.get(potion_id, 0) + potion.quantity
            )

        if error_status is None:
            ingredients = ledger.get_current_ingredients(connection)
            available_ml = [
                ingredients.red_ml,
                ingredients.green_ml,
                ingredients.blue_ml,
                ingredients.dark_ml,
            ]

            if any(
                amount_used > amount_available
                for amount_used, amount_available in zip(
                    ingredients_used,
                    available_ml,
                )
            ):
                error_status = status.HTTP_409_CONFLICT
                error_detail = "Not enough raw ingredients for this delivery"
            elif (
                ledger.get_total_potions(connection)
                + sum(potion_quantities_to_add.values())
                > 50
            ):
                error_status = status.HTTP_409_CONFLICT
                error_detail = "Not enough potion capacity for this delivery"
            elif potion_quantities_to_add:
                transaction_id = int(
                    connection.execute(
                        sqlalchemy.text(
                            """
                            INSERT INTO inventory_transactions (
                                transaction_type,
                                description
                            )
                            VALUES (
                                'bottle_delivery',
                                :description
                            )
                            RETURNING id
                            """
                        ),
                        {
                            "description": f"Bottle delivery order {order_id}",
                        },
                    ).scalar_one()
                )

                ingredient_names = ["red", "green", "blue", "dark"]
                ingredient_entries: list[dict[str, object]] = [
                    {
                        "transaction_id": transaction_id,
                        "ingredient_type": ingredient_name,
                        "change": -amount_used,
                    }
                    for ingredient_name, amount_used in zip(
                        ingredient_names,
                        ingredients_used,
                    )
                    if amount_used != 0
                ]

                if ingredient_entries:
                    connection.execute(
                        sqlalchemy.text(
                            """
                            INSERT INTO ingredient_ledger_entries (
                                transaction_id,
                                ingredient_type,
                                change
                            )
                            VALUES (
                                :transaction_id,
                                :ingredient_type,
                                :change
                            )
                            """
                        ),
                        ingredient_entries,
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
                            :potion_id,
                            :change
                        )
                        """
                    ),
                    [
                        {
                            "transaction_id": transaction_id,
                            "potion_id": potion_id,
                            "change": quantity,
                        }
                        for potion_id, quantity in potion_quantities_to_add.items()
                    ],
                )

                idempotency.complete_request(
                    connection,
                    processed_request_id,
                    status.HTTP_204_NO_CONTENT,
                    transaction_id=transaction_id,
                )
            else:
                idempotency.complete_request(
                    connection,
                    processed_request_id,
                    status.HTTP_204_NO_CONTENT,
                )

        if error_status is not None and error_detail is not None:
            idempotency.complete_request(
                connection,
                processed_request_id,
                error_status,
                response_body={"detail": error_detail},
            )

    if error_status is not None and error_detail is not None:
        raise HTTPException(
            status_code=error_status,
            detail=error_detail,
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
def get_bottle_plan() -> List[PotionMixes]:
    """
    Gets a bottle plan using ledger-based inventory balances.
    """
    with db.engine.begin() as connection:
        ingredients = ledger.get_current_ingredients(connection)
        potion_quantities = ledger.get_current_potion_quantities(connection)

        potion_rows = connection.execute(
            sqlalchemy.text(
                """
                SELECT
                    id,
                    red_ml,
                    green_ml,
                    blue_ml,
                    dark_ml
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
            quantity=potion_quantities.get(int(row.id), 0),
        )
        for row in potion_rows
    ]

    return create_bottle_plan(
        red_ml=ingredients.red_ml,
        green_ml=ingredients.green_ml,
        blue_ml=ingredients.blue_ml,
        dark_ml=ingredients.dark_ml,
        maximum_potion_capacity=50,
        current_potion_inventory=potion_inventory,
    )
