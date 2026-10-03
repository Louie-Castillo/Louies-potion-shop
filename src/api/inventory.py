from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
import sqlalchemy

from src import idempotency, ledger
from src.api import auth
from src import database as db

router = APIRouter(
    prefix="/inventory",
    tags=["inventory"],
    dependencies=[Depends(auth.get_api_key)],
)


class InventoryAudit(BaseModel):
    number_of_potions: int
    ml_in_barrels: int
    gold: int


class CapacityPlan(BaseModel):
    potion_capacity: int = Field(
        ge=0, le=10, description="Potion capacity units, max 10"
    )
    ml_capacity: int = Field(ge=0, le=10, description="ML capacity units, max 10")


@router.get("/audit", response_model=InventoryAudit)
def get_inventory():
    """
    Returns an audit of the current ledger-based inventory.
    """
    with db.engine.begin() as connection:
        gold = ledger.get_current_gold(connection)
        ingredients = ledger.get_current_ingredients(connection)
        number_of_potions = ledger.get_total_potions(connection)

    return InventoryAudit(
        number_of_potions=number_of_potions,
        ml_in_barrels=ingredients.total_ml,
        gold=gold,
    )


@router.post("/plan", response_model=CapacityPlan)
def get_capacity_plan():
    """
    Provides a daily capacity purchase plan.

    - Start with 1 capacity for 50 potions and 1 capacity for 10,000 ml of potion.
    - Each additional capacity unit costs 1000 gold.
    """
    with db.engine.begin() as connection:
        gold = ledger.get_current_gold(connection)
        ingredients = ledger.get_current_ingredients(connection)
        current_potions = ledger.get_total_potions(connection)
        capacity = ledger.get_capacity_balances(connection)

    affordable_units = max(
        0,
        (gold - 500) // ledger.CAPACITY_UNIT_COST,
    )

    if affordable_units == 0:
        return CapacityPlan(potion_capacity=0, ml_capacity=0)

    potion_utilization = current_potions / capacity.maximum_potions
    ml_utilization = ingredients.total_ml / capacity.maximum_ml
    potion_units = 0
    ml_units = 0

    capacity_options = sorted(
        [
            (potion_utilization, "potion"),
            (ml_utilization, "ml"),
        ],
        reverse=True,
    )

    for utilization, capacity_type in capacity_options:
        if utilization < 0.8 or affordable_units == 0:
            continue

        if (
            capacity_type == "potion"
            and capacity.potion_units < ledger.MAX_CAPACITY_UNITS
        ):
            potion_units = 1
            affordable_units -= 1
        elif capacity_type == "ml" and capacity.ml_units < ledger.MAX_CAPACITY_UNITS:
            ml_units = 1
            affordable_units -= 1

    return CapacityPlan(
        potion_capacity=potion_units,
        ml_capacity=ml_units,
    )


@router.post("/deliver/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def deliver_capacity_plan(capacity_purchase: CapacityPlan, order_id: int) -> None:
    """
    Processes the delivery of the planned capacity purchase. order_id is a
    unique value representing a single delivery; the call is idempotent.

    - Start with 1 capacity for 50 potions and 1 capacity for 10,000 ml of potion.
    - Each additional capacity unit costs 1000 gold.
    """
    print(f"capacity delivered: {capacity_purchase} order_id: {order_id}")
    operation_type = "capacity_delivery"
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

            detail = "Previously processed capacity delivery failed"

            if isinstance(stored_response.body, dict):
                stored_detail = stored_response.body.get("detail")
                if isinstance(stored_detail, str):
                    detail = stored_detail

            raise HTTPException(
                status_code=stored_response.status_code,
                detail=detail,
            )

        lock_query = "SELECT id FROM global_inventory WHERE id = 1"
        if connection.dialect.name == "postgresql":
            lock_query += " FOR UPDATE"
        connection.execute(sqlalchemy.text(lock_query)).one()

        capacity = ledger.get_capacity_balances(connection)
        gold = ledger.get_current_gold(connection)
        new_potion_units = capacity.potion_units + capacity_purchase.potion_capacity
        new_ml_units = capacity.ml_units + capacity_purchase.ml_capacity
        purchase_units = (
            capacity_purchase.potion_capacity + capacity_purchase.ml_capacity
        )
        purchase_cost = purchase_units * ledger.CAPACITY_UNIT_COST

        if (
            new_potion_units > ledger.MAX_CAPACITY_UNITS
            or new_ml_units > ledger.MAX_CAPACITY_UNITS
        ):
            error_status = status.HTTP_409_CONFLICT
            error_detail = "Capacity purchase exceeds the maximum capacity"
        elif purchase_cost > gold:
            error_status = status.HTTP_409_CONFLICT
            error_detail = "Not enough gold for this capacity purchase"
        elif purchase_units == 0:
            idempotency.complete_request(
                connection,
                processed_request_id,
                status.HTTP_204_NO_CONTENT,
            )
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
                            'capacity_delivery',
                            :description
                        )
                        RETURNING id
                        """
                    ),
                    {"description": f"Capacity delivery order {order_id}"},
                ).scalar_one()
            )
            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO gold_ledger_entries (
                        transaction_id,
                        change
                    )
                    VALUES (:transaction_id, :change)
                    """
                ),
                {
                    "transaction_id": transaction_id,
                    "change": -purchase_cost,
                },
            )
            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO capacity_ledger_entries (
                        transaction_id,
                        potion_capacity_change,
                        ml_capacity_change
                    )
                    VALUES (
                        :transaction_id,
                        :potion_capacity_change,
                        :ml_capacity_change
                    )
                    """
                ),
                {
                    "transaction_id": transaction_id,
                    "potion_capacity_change": capacity_purchase.potion_capacity,
                    "ml_capacity_change": capacity_purchase.ml_capacity,
                },
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
        raise HTTPException(status_code=error_status, detail=error_detail)
