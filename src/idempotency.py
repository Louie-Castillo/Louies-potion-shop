from dataclasses import dataclass

import sqlalchemy
from sqlalchemy.engine import Connection


@dataclass(frozen=True)
class StoredResponse:
    status_code: int
    body: object | None


def reserve_request(
    connection: Connection,
    operation_type: str,
    request_id: str,
) -> int | None:
    row = connection.execute(
        sqlalchemy.text(
            """
            INSERT INTO processed_requests (
                operation_type,
                request_id
            )
            VALUES (
                :operation_type,
                :request_id
            )
            ON CONFLICT (operation_type, request_id)
            DO NOTHING
            RETURNING id
            """
        ),
        {
            "operation_type": operation_type,
            "request_id": request_id,
        },
    ).one_or_none()

    if row is None:
        return None

    return int(row.id)


def get_stored_response(
    connection: Connection,
    operation_type: str,
    request_id: str,
) -> StoredResponse:
    statement = sqlalchemy.text(
        """
        SELECT response_status, response_body
        FROM processed_requests
        WHERE
            operation_type = :operation_type
            AND request_id = :request_id
        """
    ).columns(
        response_status=sqlalchemy.Integer(),
        response_body=sqlalchemy.JSON(),
    )

    row = connection.execute(
        statement,
        {
            "operation_type": operation_type,
            "request_id": request_id,
        },
    ).one()

    if row.response_status is None:
        raise RuntimeError("Processed request has no stored response")

    return StoredResponse(
        status_code=int(row.response_status),
        body=row.response_body,
    )


def complete_request(
    connection: Connection,
    processed_request_id: int,
    status_code: int,
    transaction_id: int | None = None,
    response_body: dict[str, object] | None = None,
) -> None:
    statement = sqlalchemy.text(
        """
        UPDATE processed_requests
        SET
            transaction_id = :transaction_id,
            response_status = :response_status,
            response_body = :response_body
        WHERE id = :processed_request_id
        """
    ).bindparams(
        sqlalchemy.bindparam(
            "response_body",
            type_=sqlalchemy.JSON(none_as_null=True),
        )
    )

    connection.execute(
        statement,
        {
            "processed_request_id": processed_request_id,
            "transaction_id": transaction_id,
            "response_status": status_code,
            "response_body": response_body,
        },
    )
