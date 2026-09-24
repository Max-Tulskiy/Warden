"""add policy overrides

Revision ID: d9a66181af0a
Revises: afddc26b2815
Create Date: 2026-09-24 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

import warden_server.db
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d9a66181af0a"
down_revision: str | Sequence[str] | None = "afddc26b2815"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # No row is created: an empty table means nobody has saved a policy, and the
    # server's configured values keep applying exactly as before the upgrade.
    op.create_table(
        "policy_overrides",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("max_request_window_hours", sa.Integer(), nullable=False),
        sa.Column("enrollment_token_ttl_hours", sa.Integer(), nullable=False),
        sa.Column("session_lifetime_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at", warden_server.db.UTCDateTime(timezone=True), nullable=False
        ),
        sa.Column("updated_by", sa.String(length=255), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_policy_overrides_single_row"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("policy_overrides")
