"""Reviewable HTTP contract snapshot; --check fails on uncommitted schema drift."""

import argparse
import base64
import json
from pathlib import Path

from app.bootstrap import build_container
from app.interfaces.api.app import create_api
from app.platform.settings import Settings

parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
args = parser.parse_args()
container = build_container(
    Settings(
        _env_file=None,
        database_url="sqlite:///:memory:",
        signing_key="schema-only-" * 4,
        encryption_key=base64.urlsafe_b64encode(b"s" * 32).decode(),
        position_worker_enabled=False,
        conversation_worker_enabled=False,
    )
)
schema = create_api(container).openapi()
text = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
path = Path(__file__).resolve().parents[2] / "deploy" / "contracts" / "openapi.json"
if args.check:
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        raise SystemExit("OpenAPI changed; regenerate the contract and review compatibility")
    print("OpenAPI contract matches checked-in snapshot")
else:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"Exported {len(schema['paths'])} API paths")
