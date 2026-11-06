"""Versioned permissions and approval configuration; directory attributes stay source-owned."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    schema = "org" if op.get_bind().dialect.name == "postgresql" else None
    op.add_column(
        "user",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        schema=schema,
    )
    for column in ("directory_roles", "directory_departments"):
        op.add_column(
            "user", sa.Column(column, sa.JSON(), nullable=False, server_default="[]"), schema=schema
        )
    op.add_column(
        "department",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        schema=schema,
    )
    op.add_column("department", sa.Column("parent_id", sa.String(100)), schema=schema)
    # Preserve legacy directory-derived manager roles/scopes without assigning production admins.
    users = sa.table(
        "user",
        sa.column("id", sa.String),
        sa.column("roles", sa.JSON),
        sa.column("departments", sa.JSON),
        sa.column("directory_roles", sa.JSON),
        sa.column("directory_departments", sa.JSON),
        schema=schema,
    )
    connection = op.get_bind()
    for row in connection.execute(
        sa.select(users.c.id, users.c.roles, users.c.departments)
    ).mappings():
        if "hiring_manager" in row["roles"]:
            connection.execute(
                users.update()
                .where(users.c.id == row["id"])
                .values(
                    directory_roles=["hiring_manager"],
                    directory_departments=row["departments"],
                    roles=[r for r in row["roles"] if r != "hiring_manager"],
                    departments=row["departments"]
                    if set(row["roles"]) - {"hiring_manager"}
                    else [],
                )
            )
    op.create_table(
        "configuration_lock",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        schema=schema,
    )
    op.create_table(
        "configuration_revision",
        sa.Column("kind", sa.String(20), primary_key=True),
        sa.Column("object_id", sa.String(100), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.String(64)),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        schema=schema,
    )


def downgrade():
    schema = "org" if op.get_bind().dialect.name == "postgresql" else None
    users = sa.table(
        "user",
        sa.column("id", sa.String),
        sa.column("roles", sa.JSON),
        sa.column("departments", sa.JSON),
        sa.column("directory_roles", sa.JSON),
        sa.column("directory_departments", sa.JSON),
        schema=schema,
    )
    connection = op.get_bind()
    for row in connection.execute(sa.select(users)).mappings():
        connection.execute(
            users.update()
            .where(users.c.id == row["id"])
            .values(
                roles=sorted(set(row["roles"]) | set(row["directory_roles"])),
                departments=sorted(set(row["departments"]) | set(row["directory_departments"])),
            )
        )
    op.drop_table("configuration_revision", schema=schema)
    op.drop_table("configuration_lock", schema=schema)
    op.drop_column("department", "parent_id", schema=schema)
    op.drop_column("department", "version", schema=schema)
    for column in ("directory_departments", "directory_roles", "version"):
        op.drop_column("user", column, schema=schema)
