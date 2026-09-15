import pytest
import sqlalchemy
from sqlalchemy.engine import Engine

from src.api import info


def test_current_time_is_stored_idempotently(
    monkeypatch: pytest.MonkeyPatch,
    v3_engine: Engine,
) -> None:
    monkeypatch.setattr(info.db, "engine", v3_engine)
    timestamp = info.Timestamp(day="Wednesday", hour=17)

    assert info.post_time(timestamp) is None
    assert info.post_time(timestamp) is None

    with v3_engine.begin() as connection:
        rows = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, day, hour
                FROM game_time
                """
            )
        ).all()

    assert len(rows) == 1
    assert rows[0].id == 1
    assert rows[0].day == "Wednesday"
    assert rows[0].hour == 17
