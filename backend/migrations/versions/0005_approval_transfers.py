"""Directory event receipts and transactional transfer notifications."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    schema = "req" if op.get_bind().dialect.name == "postgresql" else None
    op.create_table(
        "directory_change",
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        schema=schema,
    )
    op.create_index("ix_directory_change_user_id", "directory_change", ["user_id"], schema=schema)
    op.create_table(
        "transfer_notice",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("requisition_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        schema=schema,
    )
    op.create_index("ix_transfer_notice_user_id", "transfer_notice", ["user_id"], schema=schema)


def downgrade():
    schema = "req" if op.get_bind().dialect.name == "postgresql" else None
    op.drop_table("transfer_notice", schema=schema)
    op.drop_table("directory_change", schema=schema)
