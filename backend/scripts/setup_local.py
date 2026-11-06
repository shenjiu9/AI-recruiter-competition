"""Generate local secrets once. Run from backend/. Never overwrites an existing .env."""

import argparse
import base64
import os
import secrets
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument(
    "--sqlite", action="store_true", help="Local fallback; not a PostgreSQL substitute"
)
args = parser.parse_args()
env = Path(".env")
if env.exists():
    raise SystemExit(".env already exists; preserving current settings")
url = (
    "sqlite:///./recruiter.local.db"
    if args.sqlite
    else "postgresql+psycopg://recruiter:recruiter@localhost:5432/recruiter"
)
env.write_text(
    "ENVIRONMENT=development\nDEV_AUTH_ENABLED=true\n"
    f"DATABASE_URL={url}\nSIGNING_KEY={secrets.token_urlsafe(48)}\n"
    f"ENCRYPTION_KEY={base64.urlsafe_b64encode(os.urandom(32)).decode()}\n"
    f"DEV_LOGIN_PASSWORD={secrets.token_urlsafe(18)}\n",
    encoding="utf-8",
)
print("Created backend/.env. Local login password is DEV_LOGIN_PASSWORD in that file.")
