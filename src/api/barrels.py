from dataclasses import dataclass
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

import sqlalchemy
from src.api import auth
from src import database as db
from src import idempotency, ledger

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
        if any(proportion < 0 or proportion > 1 for proportion in potion_type):
            raise ValueError("potion_type values must be between 0 and 1")
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

    operation_type = "barrel_delivery"
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

            detail = "Previously processed barrel delivery failed"

            if isinstance(stored_response.body, dict):
                stored_detail = stored_response.body.get("detail")
                if isinstance(stored_detail, str):
                    detail = stored_detail

            raise HTTPException(
                status_code=stored_response.status_code,
                detail=detail,
            )

        if ingredients_delivered[3] > 0:
            error_status = status.HTTP_400_BAD_REQUEST
            error_detail = "Dark ingredient storage is not currently supported"
        else:
            lock_query = """
                SELECT id
                FROM global_inventory
                WHERE id = 1
            """

            if connection.dialect.name == "postgresql":
                lock_query += " FOR UPDATE"

            connection.execute(sqlalchemy.text(lock_query)).one()

            gold = ledger.get_current_gold(connection)
            ingredients = ledger.get_current_ingredients(connection)
            delivered_ml = sum(ingredients_delivered)

            if delivery.gold_paid > gold:
                error_status = status.HTTP_409_CONFLICT
                error_detail = "Not enough gold for this barrel delivery"
            elif ingredients.total_ml + delivered_ml > 10000:
                error_status = status.HTTP_409_CONFLICT
                error_detail = "Not enough capacity for this barrel delivery"
            else:
                transaction_id = int(
                    connection.execute(
                        sqlalchemy.text(
                            """
                            INSERT INTO inventory_transactions (
                                transaction_type,
                                description
                            )
                            VALUES (
                                'barrel_delivery',
                                :description
                            )
                            RETURNING id
                            """
                        ),
                        {
                            "description": f"Barrel delivery order {order_id}",
                        },
                    ).scalar_one()
                )

                if delivery.gold_paid > 0:
                    connection.execute(
                        sqlalchemy.text(
                            """
                            INSERT INTO gold_ledger_entries (
                                transaction_id,
                                change
                            )
                            VALUES (
                                :transaction_id,
                                :change
                            )
                            """
                        ),
                        {
                            "transaction_id": transaction_id,
                            "change": -delivery.gold_paid,
                        },
                    )

                ingredient_names = ["red", "green", "blue", "dark"]
                ingredient_entries: list[dict[str, object]] = [
                    {
                        "transaction_id": transaction_id,
                        "ingredient_type": ingredient_name,
                        "change": amount,
                    }
                    for ingredient_name, amount in zip(
                        ingredient_names,
                        ingredients_delivered,
                    )
                    if amount != 0
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

                idempotency.complete_request(
                    connection,
                    processed_request_id,
                    status.HTTP_204_NO_CONTENT,
                    transaction_id=transaction_id,
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
        gold = ledger.get_current_gold(connection)
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
                ORDER BY id
                """
            )
        ).all()

        game_time = connection.execute(
            sqlalchemy.text(
                """
                SELECT day, hour
                FROM game_time
                WHERE id = 1
                """
            )
        ).one()

        if (
            wholesale_catalog
            and game_time.day is not None
            and game_time.hour is not None
        ):
            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO barrel_offers (
                        game_day,
                        game_hour,
                        sku,
                        ml_per_barrel,
                        red_fraction,
                        green_fraction,
                        blue_fraction,
                        dark_fraction,
                        price,
                        quantity
                    )
                    VALUES (
                        :game_day,
                        :game_hour,
                        :sku,
                        :ml_per_barrel,
                        :red_fraction,
                        :green_fraction,
                        :blue_fraction,
                        :dark_fraction,
                        :price,
                        :quantity
                    )
                    ON CONFLICT DO NOTHING
                    """
                ),
                [
                    {
                        "game_day": game_time.day,
                        "game_hour": game_time.hour,
                        "sku": barrel.sku,
                        "ml_per_barrel": barrel.ml_per_barrel,
                        "red_fraction": barrel.potion_type[0],
                        "green_fraction": barrel.potion_type[1],
                        "blue_fraction": barrel.potion_type[2],
                        "dark_fraction": barrel.potion_type[3],
                        "price": barrel.price,
                        "quantity": barrel.quantity,
                    }
                    for barrel in wholesale_catalog
                ],
            )

    target_potion = min(
        potion_rows,
        key=lambda row: (
            potion_quantities.get(int(row.id), 0),
            -sum(
                amount > 0
                for amount in (
                    row.red_ml,
                    row.green_ml,
                    row.blue_ml,
                    row.dark_ml,
                )
            ),
            int(row.id),
        ),
        default=None,
    )

    if target_potion is None:
        return []

    return create_barrel_plan(
        gold=gold,
        max_barrel_capacity=10000,
        current_ml=[
            ingredients.red_ml,
            ingredients.green_ml,
            ingredients.blue_ml,
            ingredients.dark_ml,
        ],
        target_potion_type=[
            target_potion.red_ml,
            target_potion.green_ml,
            target_potion.blue_ml,
            target_potion.dark_ml,
        ],
        wholesale_catalog=wholesale_catalog,
    )
