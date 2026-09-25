"""index events by agent and occurred_at

Revision ID: 5e46afcba6a5
Revises: d9a66181af0a
Create Date: 2026-09-22 17:01:47.768532

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5e46afcba6a5"
down_revision: str | Sequence[str] | None = "d9a66181af0a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "ix_events_agent_id_occurred_at", "events", ["agent_id", "occurred_at"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_events_agent_id_occurred_at", table_name="events")
