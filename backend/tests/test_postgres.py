from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.modules.requisition.adapters.orm import RequisitionRecord
from app.platform.records import EventRecord


@pytest.mark.postgres
def test_postgres_concurrent_idempotency_and_audit_immutability(container, client, login, fields):
    if container.db.engine.dialect.name != "postgresql":
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database")
    headers = login(key="same-concurrent-request")

    def submit(_):
        response = client.post("/api/v1/hr/requisitions", json=fields, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(submit, range(4)))
    assert all(response == responses[0] for response in responses)
    with container.db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(RequisitionRecord)) == 1
        assert session.scalar(select(func.count()).select_from(EventRecord)) == 1
    with pytest.raises(DBAPIError, match="append-only"):
        with container.db.engine.begin() as connection:
            connection.execute(text("UPDATE platform.audit_log SET action = 'tampered'"))
