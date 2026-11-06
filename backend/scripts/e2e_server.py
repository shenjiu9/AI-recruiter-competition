"""Disposable local API for browser tests; never touches backend/.env or user data."""

import base64
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from alembic import command
from alembic.config import Config

from app.bootstrap import build_container
from app.dev_seed import seed
from app.interfaces.api.app import create_api
from app.modules.org.adapters.repository import DepartmentRecord, UserRecord
from app.platform.settings import Settings

with TemporaryDirectory(prefix="recruiter-e2e-") as directory:
    os.environ.update(
        DATABASE_URL=f"sqlite:///{Path(directory) / 'browser.db'}",
        SIGNING_KEY="e2e-only-signing-key-not-for-production-00000000",
        ENCRYPTION_KEY=base64.urlsafe_b64encode(b"e" * 32).decode(),
        DEV_AUTH_ENABLED="true",
        DEV_LOGIN_PASSWORD="e2e-only-password",
        ENVIRONMENT="development",
        CANDIDATE_PORTAL_URL="http://127.0.0.1:5185",
    )
    command.upgrade(Config("alembic.ini"), "head")
    container = build_container(Settings())
    seed(container)
    # Browser fixtures live only in this disposable database, never in demo/production seed.
    with container.db.sessions.begin() as db:
        db.add(
            DepartmentRecord(
                id="客服测试小组",
                parent_id="客服中心",
                policy=dict(db.get(DepartmentRecord, "客服中心").policy),
            )
        )
        for number in range(25):
            db.add(
                UserRecord(
                    id=f"z-person-{number:02}",
                    name="同名测试员工" if number < 2 else f"目录测试员工{number}",
                    roles=["recruiter"],
                    departments=["客服中心"],
                )
            )
        db.add(
            UserRecord(
                id="z-left", name="历史离职员工", active=False, roles=[], departments=["客服中心"]
            )
        )
    from e2e_interview_fixture import seed_finished_interview

    seed_finished_interview(container)
    uvicorn.run(create_api(container), host="127.0.0.1", port=8010, log_level="warning")
