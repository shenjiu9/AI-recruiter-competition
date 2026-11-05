import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_directory_backfill_and_upgrade_downgrade_preserve_legacy_records(tmp_path):
    database = tmp_path / "migration.db"
    environment = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{database}",
        "SIGNING_KEY": "migration-test-signing-key-" * 3,
        "ENCRYPTION_KEY": "ZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWU=",
    }

    def migrate(*args):
        subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=Path(__file__).parents[1],
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )

    migrate("upgrade", "0003")
    with sqlite3.connect(database) as db:
        db.execute(
            'INSERT INTO "user" (id, name, roles, departments, active) VALUES (?, ?, ?, ?, ?)',
            ("legacy", "原经理", json.dumps(["hiring_manager"]), json.dumps(["原部门"]), True),
        )
    migrate("upgrade", "head")
    with sqlite3.connect(database) as db:
        roles, departments, version = db.execute(
            'SELECT directory_roles, directory_departments, version FROM "user"'
        ).fetchone()
        assert (
            json.loads(roles) == ["hiring_manager"]
            and json.loads(departments) == ["原部门"]
            and version == 1
        )
    migrate("downgrade", "0003")
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT name FROM "user"').fetchone()[0] == "原经理"
        assert json.loads(db.execute('SELECT roles FROM "user"').fetchone()[0]) == [
            "hiring_manager"
        ]
        assert json.loads(db.execute('SELECT departments FROM "user"').fetchone()[0]) == ["原部门"]
        assert "directory_roles" not in {r[1] for r in db.execute('PRAGMA table_info("user")')}
    migrate("upgrade", "head")
    migrate("check")
