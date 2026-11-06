"""Encrypted PostgreSQL snapshot and isolated restore drill for local Compose.

Never restores over the application's database. Preserve ENCRYPTION_KEY separately.
"""

import argparse
import base64
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from dotenv import dotenv_values
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    str(ROOT / "backend" / ".env"),
    "-f",
    str(ROOT / "deploy" / "compose.yaml"),
]


def counts(connection):
    tables = connection.execute(
        "SELECT schemaname, tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2"
    ).fetchall()
    return {
        schema + "." + table: connection.execute(
            sql.SQL("SELECT count(*) FROM {}.{}").format(
                sql.Identifier(schema), sql.Identifier(table)
            )
        ).fetchone()[0]
        for schema, table in tables
    }


def docker(arguments, data=None):
    result = subprocess.run(
        COMPOSE + ["exec", "-T", "postgres", *arguments],
        cwd=ROOT,
        input=data,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        # pg_dump may include database/connection information; don't echo it.
        raise SystemExit("PostgreSQL backup/restore command failed: " + arguments[0])
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["backup", "verify"])
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    values = dotenv_values(ROOT / "backend" / ".env")
    crypto = Fernet(values["ENCRYPTION_KEY"].encode())
    records_crypto = AESGCM(base64.urlsafe_b64decode(values["ENCRYPTION_KEY"]))
    connect = {
        "host": "127.0.0.1",
        "port": 5432,
        "user": "recruiter",
        "password": values.get("POSTGRES_PASSWORD") or "recruiter",
    }
    if args.action == "backup":
        if args.file.exists():
            raise SystemExit("Choose a new backup file; existing backups are never overwritten")
        with psycopg.connect(**connect, dbname="recruiter") as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            snapshot = connection.execute("SELECT pg_export_snapshot()").fetchone()[0]
            manifest = {
                "format": 1,
                "created_at": datetime.now(UTC).isoformat(),
                "counts": counts(connection),
            }
            dump = docker(
                [
                    "pg_dump",
                    "-U",
                    "recruiter",
                    "-d",
                    "recruiter",
                    "-Fc",
                    "--no-owner",
                    "--no-acl",
                    "--snapshot=" + snapshot,
                ]
            )
        manifest["dump"] = base64.b64encode(dump).decode()
        args.file.parent.mkdir(parents=True, exist_ok=True)
        args.file.write_bytes(crypto.encrypt(json.dumps(manifest).encode()))
        print(
            json.dumps(
                {
                    "backup": str(args.file.resolve()),
                    "tables": len(manifest["counts"]),
                    "encrypted": True,
                }
            )
        )
        return
    manifest = json.loads(crypto.decrypt(args.file.read_bytes()))
    if manifest.get("format") != 1:
        raise SystemExit("Unsupported backup format")
    database = "recruiter_restore_" + uuid4().hex[:12] + "_test"
    with psycopg.connect(**connect, dbname="postgres", autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        try:
            docker(
                [
                    "pg_restore",
                    "-U",
                    "recruiter",
                    "-d",
                    database,
                    "--no-owner",
                    "--no-acl",
                    "--exit-on-error",
                ],
                base64.b64decode(manifest["dump"]),
            )
            with psycopg.connect(**connect, dbname=database) as restored:
                actual = counts(restored)
                if actual != manifest["counts"]:
                    raise SystemExit(
                        "Restore row counts differ from the consistent backup snapshot"
                    )
                version = restored.execute(
                    "SELECT version_num FROM platform.alembic_version"
                ).fetchone()[0]
                # Verify encrypted records can still be decoded using the separately retained key.
                encrypted = restored.execute(
                    "SELECT table_schema, table_name FROM information_schema.columns WHERE column_name='data' AND data_type='bytea' AND table_schema NOT IN ('pg_catalog','information_schema')"
                ).fetchall()
                checked = 0
                for schema, table in encrypted:
                    purpose = (
                        sql.SQL("band_id || ':' || version")
                        if (schema, table) == ("org", "salary_revision")
                        else sql.Identifier(
                            "requisition_id" if (schema, table) == ("pos", "generation") else "id"
                        )
                    )
                    for identifier, value in restored.execute(
                        sql.SQL("SELECT {}, data FROM {}.{} LIMIT 5").format(
                            purpose, sql.Identifier(schema), sql.Identifier(table)
                        )
                    ):
                        value = bytes(value)
                        records_crypto.decrypt(value[:12], value[12:], identifier.encode())
                        checked += 1
            print(
                json.dumps(
                    {
                        "restore_verified": True,
                        "schema": version,
                        "tables": len(actual),
                        "encrypted_records_checked": checked,
                        "application_database_untouched": True,
                    }
                )
            )
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))


if __name__ == "__main__":
    main()
