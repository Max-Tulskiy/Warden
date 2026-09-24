"""index audit log by occurred_at

Revision ID: 5b03c4109d6c
Revises: ee7eb82ccbe5
Create Date: 2026-09-24 13:47:23.333932

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5b03c4109d6c"
down_revision: str | Sequence[str] | None = "ee7eb82ccbe5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index("ix_audit_log_occurred_at", "audit_log", ["occurred_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_audit_log_occurred_at", table_name="audit_log")
