"""Versioned, effective-dated encrypted salary master data. No inferred production budgets."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "salary_band",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("series", sa.String(80), nullable=False),
        sa.Column("grade", sa.String(40), nullable=False),
        sa.Column("city", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("series", "grade", "city", name="salary_dimensions"),
        schema="org",
    )
    op.create_table(
        "salary_revision",
        sa.Column("band_id", sa.String(64), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("updated_on", sa.Date(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        schema="org",
    )


def downgrade():
    op.drop_table("salary_revision", schema="org")
    op.drop_table("salary_band", schema="org")
