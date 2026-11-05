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
from app.platform.settings import Settings

with TemporaryDirectory(prefix="recruiter-e2e-") as directory:
    os.environ.update(
        DATABASE_URL=f"sqlite:///{Path(directory) / 'browser.db'}",
        SIGNING_KEY="e2e-only-signing-key-not-for-production-00000000",
        ENCRYPTION_KEY=base64.urlsafe_b64encode(b"e" * 32).decode(),
        DEV_AUTH_ENABLED="true",
        DEV_LOGIN_PASSWORD="e2e-only-password",
        ENVIRONMENT="development",
    )
    command.upgrade(Config("alembic.ini"), "head")
    container = build_container(Settings())
    seed(container)
    uvicorn.run(create_api(container), host="127.0.0.1", port=8010, log_level="warning")
