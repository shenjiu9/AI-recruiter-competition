import base64
import os
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.bootstrap import build_container
from app.dev_seed import seed
from app.interfaces.api.app import create_api
from app.platform.database import Base
from app.platform.settings import Settings


@pytest.fixture
def container(tmp_path):
    postgres_url = os.environ.get("TEST_DATABASE_URL")
    if postgres_url and not make_url(postgres_url).database.endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must point to a disposable database ending in _test")
    settings = Settings(
        _env_file=None,
        database_url=postgres_url or f"sqlite:///{tmp_path / 'test.db'}",
        signing_key="test-signing-key-" * 4,
        encryption_key=base64.urlsafe_b64encode(b"e" * 32).decode(),
        dev_auth_enabled=True,
        dev_login_password="test-password",
        position_worker_enabled=False,
        conversation_worker_enabled=False,
    )
    container = build_container(settings)
    if postgres_url:
        with container.db.engine.begin() as connection:
            tables = ", ".join(
                f'"{table.schema}"."{table.name}"' for table in Base.metadata.sorted_tables
            )
            connection.execute(text(f"TRUNCATE {tables} CASCADE"))
    else:
        Base.metadata.create_all(container.db.engine)
    seed(container)
    yield container
    container.db.engine.dispose()


@pytest.fixture
def client(container):
    with TestClient(create_api(container)) as client:
        yield client


@pytest.fixture
def login(client):
    def headers(user="hr", key="test-request"):
        response = client.post(
            "/api/v1/auth/dev-login", json={"user_id": user, "password": "test-password"}
        )
        assert response.status_code == 200, response.text
        return {"Authorization": "Bearer " + response.json()["token"], "Idempotency-Key": key}

    return headers


@pytest.fixture
def fields():
    return {
        "recruitType": "社招",
        "dept": "客服中心",
        "employmentType": "正式",
        "reqType": "新增",
        "headcount": "2",
        "title": "客服专员",
        "series": "客服",
        "level": "P3",
        "city": "深圳",
        "reportTo": "何美玲",
        "expectedOnboard": (datetime.now(UTC).date() + timedelta(days=30)).isoformat(),
        "salary": "8-12K/月×13",
        "reason": "业务扩展",
        "duties": "处理客户咨询",
        "requirements": "沟通和问题解决能力",
    }
