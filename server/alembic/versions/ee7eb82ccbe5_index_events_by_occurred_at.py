"""index events by occurred_at

Revision ID: ee7eb82ccbe5
Revises: 59fb180e4891
Create Date: 2026-09-20 22:15:28.103966

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ee7eb82ccbe5"
down_revision: str | Sequence[str] | None = "59fb180e4891"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index("ix_events_occurred_at", "events", ["occurred_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_events_occurred_at", table_name="events")
