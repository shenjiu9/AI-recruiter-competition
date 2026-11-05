"""Annual headcount capacity and final-approval reservation ledger.

No production budget is inferred from the old demo policy. Maintainers must enter
their actual plans; the explicit development seed installs demo budgets only.
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "headcount",
        sa.Column("dept", sa.String(100), primary_key=True),
        sa.Column("year", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("planned", sa.Integer(), nullable=False),
        sa.Column("used", sa.Integer(), nullable=False),
        sa.Column("reserved", sa.Integer(), nullable=False),
        sa.Column("frozen", sa.Boolean(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("updated_on", sa.Date(), nullable=False),
        sa.CheckConstraint(
            "planned >= 0 AND used >= 0 AND reserved >= 0 AND planned >= used + reserved",
            name="capacity",
        ),
        schema="org",
    )
    op.create_table(
        "hc_reservation",
        sa.Column("requisition_id", sa.String(64), primary_key=True),
        sa.Column("dept", sa.String(100), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        schema="org",
    )


def downgrade():
    op.drop_table("hc_reservation", schema="org")
    op.drop_table("headcount", schema="org")
