from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
import sqlalchemy
from src.api import auth
from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional, Sequence
from src import database as db
from src import idempotency, ledger

router = APIRouter(
    prefix="/carts",
    tags=["cart"],
    dependencies=[Depends(auth.get_api_key)],
)


class SearchSortOptions(str, Enum):
    customer_name = "customer_name"
    item_sku = "item_sku"
    line_item_total = "line_item_total"
    timestamp = "timestamp"


class SearchSortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


class LineItem(BaseModel):
    line_item_id: int
    item_sku: str
    customer_name: str
    line_item_total: int
    timestamp: str


class SearchResponse(BaseModel):
    previous: Optional[str] = None
    next: Optional[str] = None
    results: List[LineItem]


def format_search_timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        parsed_timestamp = value
    else:
        timestamp_text = str(value).replace(" ", "T", 1)

        try:
            parsed_timestamp = datetime.fromisoformat(
                timestamp_text.replace("Z", "+00:00")
            )
        except ValueError:
            return timestamp_text

    if parsed_timestamp.tzinfo is None:
        parsed_timestamp = parsed_timestamp.replace(tzinfo=timezone.utc)

    return parsed_timestamp.isoformat().replace("+00:00", "Z")


@router.get("/search/", response_model=SearchResponse, tags=["search"])
def search_orders(
    customer_name: str = "",
    potion_sku: str = "",
    search_page: str = "",
    sort_col: SearchSortOptions = SearchSortOptions.timestamp,
    sort_order: SearchSortOrder = SearchSortOrder.desc,
) -> SearchResponse:
    """
    Search for cart line items by customer name and/or potion sku.
    """
    conditions = [
        "carts.checked_out = TRUE",
        "carts.checked_out_at IS NOT NULL",
    ]
    parameters: dict[str, object] = {}

    normalized_customer_name = customer_name.strip().lower()
    normalized_potion_sku = potion_sku.strip().lower()

    if normalized_customer_name:
        conditions.append("LOWER(carts.customer_name) LIKE :customer_name")
        parameters["customer_name"] = f"%{normalized_customer_name}%"

    if normalized_potion_sku:
        conditions.append("LOWER(potions.sku) LIKE :potion_sku")
        parameters["potion_sku"] = f"%{normalized_potion_sku}%"

    where_clause = " AND ".join(conditions)

    with db.engine.begin() as connection:
        rows = connection.execute(
            sqlalchemy.text(
                f"""
                SELECT
                    cart_items.id AS line_item_id,
                    potions.sku AS item_sku,
                    carts.customer_name,
                    cart_items.quantity * potions.price AS line_item_total,
                    carts.checked_out_at AS timestamp
                FROM carts
                JOIN cart_items
                    ON cart_items.cart_id = carts.id
                JOIN potions
                    ON potions.id = cart_items.potion_id
                WHERE {where_clause}
                ORDER BY
                    carts.checked_out_at DESC,
                    cart_items.id DESC
                """
            ),
            parameters,
        ).all()

    return SearchResponse(
        previous=None,
        next=None,
        results=[
            LineItem(
                line_item_id=int(row.line_item_id),
                item_sku=str(row.item_sku),
                customer_name=str(row.customer_name),
                line_item_total=int(row.line_item_total),
                timestamp=format_search_timestamp(row.timestamp),
            )
            for row in rows
        ],
    )


class Customer(BaseModel):
    customer_id: str
    customer_name: str
    character_class: str
    character_species: str
    level: int = Field(ge=1, le=20)


@router.post("/visits/{visit_id}", status_code=status.HTTP_204_NO_CONTENT)
def post_visits(visit_id: int, customers: List[Customer]):
    """
    Shares the customers that visited the store on that tick.
    """
    print(customers)
    pass


class CartCreateResponse(BaseModel):
    cart_id: int


@router.post("/", response_model=CartCreateResponse)
def create_cart(new_cart: Customer) -> CartCreateResponse:
    """
    Returns the customer's current open cart or creates a new one.
    """
    with db.engine.begin() as connection:
        open_cart_id = connection.execute(
            sqlalchemy.text(
                """
                SELECT id
                FROM carts
                WHERE
                    customer_id = :customer_id
                    AND checked_out = FALSE
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            {"customer_id": new_cart.customer_id},
        ).scalar_one_or_none()

        if open_cart_id is not None:
            return CartCreateResponse(cart_id=int(open_cart_id))

        cart_id = int(
            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO carts (
                    customer_id,
                    customer_name,
                    character_class,
                    character_species,
                    level
                    )
                    VALUES (
                    :customer_id,
                    :customer_name,
                    :character_class,
                    :character_species,
                    :level
                    )
                    RETURNING id
                    """
                ),
                [
                    {
                        "customer_id": new_cart.customer_id,
                        "customer_name": new_cart.customer_name,
                        "character_class": new_cart.character_class,
                        "character_species": new_cart.character_species,
                        "level": new_cart.level,
                    }
                ],
            ).scalar_one()
        )

    return CartCreateResponse(cart_id=cart_id)


class CartItem(BaseModel):
    quantity: int = Field(ge=1, description="Quantity must be at least 1")


@router.post("/{cart_id}/items/{item_sku}", status_code=status.HTTP_204_NO_CONTENT)
def set_item_quantity(cart_id: int, item_sku: str, cart_item: CartItem):
    with db.engine.begin() as connection:
        cart = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, checked_out
                FROM carts
                WHERE id = :cart_id
                """
            ),
            {"cart_id": cart_id},
        ).one_or_none()

        if cart is None:
            raise HTTPException(status_code=404, detail="Cart not found")

        if cart.checked_out:
            raise HTTPException(
                status_code=400,
                detail="Cannot modify a checked-out cart",
            )

        potion_id = connection.execute(
            sqlalchemy.text(
                """
                SELECT id
                FROM potions
                WHERE sku = :item_sku
                """
            ),
            {"item_sku": item_sku},
        ).scalar_one_or_none()

        if potion_id is None:
            raise HTTPException(status_code=404, detail="Potion not found")

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO cart_items (
                    cart_id,
                    potion_id,
                    quantity
                )
                VALUES (
                    :cart_id,
                    :potion_id,
                    :quantity
                )
                ON CONFLICT (cart_id, potion_id)
                DO UPDATE SET
                    quantity = EXCLUDED.quantity
                """
            ),
            {
                "cart_id": cart_id,
                "potion_id": potion_id,
                "quantity": cart_item.quantity,
            },
        )


class CheckoutResponse(BaseModel):
    total_potions_bought: int
    total_gold_paid: int


class CartCheckout(BaseModel):
    payment: str


@router.post("/{cart_id}/checkout", response_model=CheckoutResponse)
def checkout(cart_id: int, cart_checkout: CartCheckout) -> CheckoutResponse:
    """
    Checks out a persistent cart using database potion prices and inventory.
    """
    operation_type = "checkout"
    request_id = str(cart_id)
    error_status: int | None = None
    error_detail: str | None = None
    checkout_response: CheckoutResponse | None = None

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

            if stored_response.status_code == status.HTTP_200_OK:
                return CheckoutResponse.model_validate(stored_response.body)

            detail = "Previously processed checkout failed"

            if isinstance(stored_response.body, dict):
                stored_detail = stored_response.body.get("detail")
                if isinstance(stored_detail, str):
                    detail = stored_detail

            raise HTTPException(
                status_code=stored_response.status_code,
                detail=detail,
            )

        inventory_lock_query = """
            SELECT id
            FROM global_inventory
            WHERE id = 1
        """
        cart_query = """
            SELECT id, checked_out
            FROM carts
            WHERE id = :cart_id
        """

        if connection.dialect.name == "postgresql":
            inventory_lock_query += " FOR UPDATE"
            cart_query += " FOR UPDATE"

        connection.execute(sqlalchemy.text(inventory_lock_query)).one()
        cart = connection.execute(
            sqlalchemy.text(cart_query),
            {"cart_id": cart_id},
        ).one_or_none()

        items: Sequence[Any] = []

        if cart is None:
            error_status = status.HTTP_404_NOT_FOUND
            error_detail = "Cart not found"
        elif cart.checked_out:
            error_status = status.HTTP_400_BAD_REQUEST
            error_detail = "Cart has already been checked out"
        else:
            items = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT
                        p.id AS potion_id,
                        p.sku,
                        p.price,
                        ci.quantity AS requested_quantity
                    FROM cart_items AS ci
                    JOIN potions AS p
                        ON p.id = ci.potion_id
                    WHERE ci.cart_id = :cart_id
                    ORDER BY p.id
                    """
                ),
                {"cart_id": cart_id},
            ).all()

            if not items:
                error_status = status.HTTP_400_BAD_REQUEST
                error_detail = "Cannot checkout an empty cart"

        if error_status is None:
            potion_quantities = ledger.get_current_potion_quantities(connection)

            for item in items:
                available_quantity = potion_quantities.get(int(item.potion_id), 0)

                if item.requested_quantity > available_quantity:
                    error_status = status.HTTP_409_CONFLICT
                    error_detail = f"Not enough inventory for {item.sku}"
                    break

        if error_status is None:
            total_potions_bought = sum(item.requested_quantity for item in items)
            total_gold_paid = sum(
                item.requested_quantity * item.price for item in items
            )
            game_time = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT day, hour
                    FROM game_time
                    WHERE id = 1
                    """
                )
            ).one()

            transaction_id = int(
                connection.execute(
                    sqlalchemy.text(
                        """
                        INSERT INTO inventory_transactions (
                            transaction_type,
                            cart_id,
                            description,
                            game_day,
                            game_hour
                        )
                        VALUES (
                            'checkout',
                            :cart_id,
                            :description,
                            :game_day,
                            :game_hour
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "cart_id": cart_id,
                        "description": f"Checkout for cart {cart_id}",
                        "game_day": game_time.day,
                        "game_hour": game_time.hour,
                    },
                ).scalar_one()
            )

            if total_gold_paid != 0:
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
                        "change": total_gold_paid,
                    },
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
                        "potion_id": item.potion_id,
                        "change": -item.requested_quantity,
                    }
                    for item in items
                ],
            )

            connection.execute(
                sqlalchemy.text(
                    """
                    UPDATE carts
                    SET
                        payment = :payment,
                        checked_out = TRUE,
                        checked_out_at = CURRENT_TIMESTAMP
                    WHERE id = :cart_id
                    """
                ),
                {
                    "payment": cart_checkout.payment,
                    "cart_id": cart_id,
                },
            )

            checkout_response = CheckoutResponse(
                total_potions_bought=total_potions_bought,
                total_gold_paid=total_gold_paid,
            )
            idempotency.complete_request(
                connection,
                processed_request_id,
                status.HTTP_200_OK,
                transaction_id=transaction_id,
                response_body=checkout_response.model_dump(),
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

    if checkout_response is None:
        raise RuntimeError("Checkout completed without a response")

    return checkout_response
