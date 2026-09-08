from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
import sqlalchemy
from src.api import auth
from enum import Enum
from typing import List, Optional
from src import database as db

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


@router.get("/search/", response_model=SearchResponse, tags=["search"])
def search_orders(
    customer_name: str = "",
    potion_sku: str = "",
    search_page: str = "",
    sort_col: SearchSortOptions = SearchSortOptions.timestamp,
    sort_order: SearchSortOrder = SearchSortOrder.desc,
):
    """
    Search for cart line items by customer name and/or potion sku.
    """
    return SearchResponse(
        previous=None,
        next=None,
        results=[
            LineItem(
                line_item_id=1,
                item_sku="1 oblivion potion",
                customer_name="Scaramouche",
                line_item_total=50,
                timestamp="2021-01-01T00:00:00Z",
            )
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
def create_cart(new_cart: Customer):
    """
    Creates a new cart for a specific customer.
    """
    with db.engine.begin() as connection:
        cart_id = connection.execute(
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
def checkout(cart_id: int, cart_checkout: CartCheckout):
    """
    Checks out a persistent cart using database potion prices and inventory.
    """
    with db.engine.begin() as connection:
        cart = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, checked_out
                FROM carts
                WHERE id = :cart_id
                FOR UPDATE
                """
            ),
            {"cart_id": cart_id},
        ).one_or_none()

        if cart is None:
            raise HTTPException(status_code=404, detail="Cart not found")

        if cart.checked_out:
            raise HTTPException(
                status_code=400,
                detail="Cart has already been checked out",
            )

        items = connection.execute(
            sqlalchemy.text(
                """
                SELECT
                    p.id AS potion_id,
                    p.sku,
                    p.price,
                    p.quantity AS available_quantity,
                    ci.quantity AS requested_quantity
                FROM cart_items AS ci
                JOIN potions AS p
                    ON p.id = ci.potion_id
                WHERE ci.cart_id = :cart_id
                ORDER BY p.id
                FOR UPDATE OF p
                """
            ),
            {"cart_id": cart_id},
        ).all()

        if not items:
            raise HTTPException(
                status_code=400,
                detail="Cannot checkout an empty cart",
            )

        for item in items:
            if item.requested_quantity > item.available_quantity:
                raise HTTPException(
                    status_code=409,
                    detail=f"Not enough inventory for {item.sku}",
                )

        total_potions_bought = sum(item.requested_quantity for item in items)
        total_gold_paid = sum(item.requested_quantity * item.price for item in items)

        connection.execute(
            sqlalchemy.text(
                """
                UPDATE potions
                SET quantity = quantity - :quantity
                WHERE id = :potion_id
                """
            ),
            [
                {
                    "quantity": item.requested_quantity,
                    "potion_id": item.potion_id,
                }
                for item in items
            ],
        )

        connection.execute(
            sqlalchemy.text(
                """
                UPDATE global_inventory
                SET gold = gold + :total_gold_paid
                WHERE id = 1
                """
            ),
            {"total_gold_paid": total_gold_paid},
        )

        connection.execute(
            sqlalchemy.text(
                """
                UPDATE carts
                SET
                    payment = :payment,
                    checked_out = TRUE,
                    checked_out_at = now()
                WHERE id = :cart_id
                """
            ),
            {
                "payment": cart_checkout.payment,
                "cart_id": cart_id,
            },
        )

    return CheckoutResponse(
        total_potions_bought=total_potions_bought,
        total_gold_paid=total_gold_paid,
    )
