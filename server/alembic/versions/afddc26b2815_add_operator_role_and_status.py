"""add operator role and status

Revision ID: afddc26b2815
Revises: d23c48cef8fe
Create Date: 2026-09-24 15:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "afddc26b2815"
down_revision: str | Sequence[str] | None = "d23c48cef8fe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Every account that exists today is a full administrator, so that is what
    # the backfill must make it: the temporary server default fills the rows
    # that are already there, and is dropped again straight afterwards. The
    # finished schema has no default for `role`, so a raw insert that leaves it
    # out is refused instead of silently creating an administrator.
    op.add_column(
        "operators",
        sa.Column(
            "role",
            sa.Enum("ADMIN", "VIEWER", name="operatorrole", native_enum=False),
            nullable=False,
            server_default="ADMIN",
        ),
    )
    op.add_column(
        "operators",
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "DISABLED", name="operatorstatus", native_enum=False),
            nullable=False,
            server_default="ACTIVE",
        ),
    )
    with op.batch_alter_table("operators") as batch:
        batch.alter_column("role", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("operators") as batch:
        batch.drop_column("status")
        batch.drop_column("role")
