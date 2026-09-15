from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Annotated
import sqlalchemy
from src import database as db
from src import ledger

router = APIRouter()


class CatalogItem(BaseModel):
    sku: Annotated[str, Field(pattern=r"^[a-zA-Z0-9_]{1,20}$")]
    name: str
    quantity: Annotated[int, Field(ge=1, le=10000)]
    price: Annotated[int, Field(ge=1, le=500)]
    potion_type: List[int] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Must contain exactly 4 elements: [r, g, b, d]",
    )


def create_catalog() -> List[CatalogItem]:
    with db.engine.begin() as connection:
        potion_quantities = ledger.get_current_potion_quantities(connection)

        rows = connection.execute(
            sqlalchemy.text(
                """
                SELECT
                    id,
                    sku,
                    name,
                    price,
                    red_ml,
                    green_ml,
                    blue_ml,
                    dark_ml
                FROM potions
                ORDER BY id
                """
            )
        ).all()

    catalog_items: List[CatalogItem] = []

    for row in rows:
        quantity = potion_quantities.get(int(row.id), 0)

        if quantity <= 0:
            continue

        catalog_items.append(
            CatalogItem(
                sku=row.sku,
                name=row.name,
                quantity=quantity,
                price=row.price,
                potion_type=[
                    row.red_ml,
                    row.green_ml,
                    row.blue_ml,
                    row.dark_ml,
                ],
            )
        )

        if len(catalog_items) == 6:
            break

    return catalog_items


@router.get("/catalog/", tags=["catalog"], response_model=List[CatalogItem])
def get_catalog() -> List[CatalogItem]:
    """
    Retrieves the catalog of items. Each unique item combination should have only a single price.
    You can have at most 6 potion SKUs offered in your catalog at one time.
    """
    return create_catalog()
