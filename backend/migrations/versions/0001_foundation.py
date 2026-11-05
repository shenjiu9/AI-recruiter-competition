"""Platform, org and requisition tables. Immutable initial migration."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("departments", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        schema="org",
    )
    op.create_table(
        "department",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("policy", sa.JSON(), nullable=False),
        schema="org",
    )
    op.create_table(
        "requisition",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("creator_id", sa.String(64), nullable=False),
        sa.Column("manager_id", sa.String(64), nullable=False),
        sa.Column("dept", sa.String(100), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("confidential", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        schema="req",
    )
    for column in ("creator_id", "dept", "status", "created_at"):
        op.create_index(f"ix_requisition_{column}", "requisition", [column], schema="req")
    op.create_table(
        "requisition_access",
        sa.Column("requisition_id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), primary_key=True),
        schema="req",
    )
    op.create_table(
        "event",
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("type", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("partition_key", sa.String(80), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("origin_event_id", sa.String(64)),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        schema="platform",
    )
    for column in ("type", "partition_key"):
        op.create_index(f"ix_event_{column}", "event", [column], schema="platform")
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("object_id", sa.String(64), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("before", sa.JSON()),
        sa.Column("after", sa.JSON(), nullable=False),
        schema="platform",
    )
    op.create_index("ix_audit_log_object_id", "audit_log", ["object_id"], schema="platform")
    op.create_table(
        "idempotency",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("response", sa.LargeBinary()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        schema="platform",
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """CREATE FUNCTION platform.reject_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'audit_log is append-only'; END; $$"""
        )
        op.execute(
            "CREATE TRIGGER audit_immutable BEFORE UPDATE OR DELETE ON platform.audit_log FOR EACH ROW EXECUTE FUNCTION platform.reject_audit_mutation()"
        )


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER audit_immutable ON platform.audit_log")
        op.execute("DROP FUNCTION platform.reject_audit_mutation()")
    for schema, table in [
        ("platform", "idempotency"),
        ("platform", "audit_log"),
        ("platform", "event"),
        ("req", "requisition_access"),
        ("req", "requisition"),
        ("org", "department"),
        ("org", "user"),
    ]:
        op.drop_table(table, schema=schema)
