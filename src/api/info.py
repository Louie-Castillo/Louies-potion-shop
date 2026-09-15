from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
import sqlalchemy

from src.api import auth
from src import database as db

router = APIRouter(
    prefix="/info",
    tags=["info"],
    dependencies=[Depends(auth.get_api_key)],
)


class Timestamp(BaseModel):
    day: str
    hour: int = Field(ge=0, le=23)


@router.post("/current_time", status_code=status.HTTP_204_NO_CONTENT)
def post_time(timestamp: Timestamp) -> None:
    """
    Shares what the latest time (in game time) is.
    """
    with db.engine.begin() as connection:
        current_time = connection.execute(
            sqlalchemy.text(
                """
                SELECT day, hour
                FROM game_time
                WHERE id = 1
                """
            )
        ).one()

        if current_time.day != timestamp.day or current_time.hour != timestamp.hour:
            connection.execute(
                sqlalchemy.text(
                    """
                    UPDATE game_time
                    SET
                        day = :day,
                        hour = :hour,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                    """
                ),
                {
                    "day": timestamp.day,
                    "hour": timestamp.hour,
                },
            )
