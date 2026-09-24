"""add operator token version

Revision ID: d23c48cef8fe
Revises: 5b03c4109d6c
Create Date: 2026-09-24 14:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d23c48cef8fe"
down_revision: str | Sequence[str] | None = "5b03c4109d6c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # The server default fills the rows that already exist, so every current
    # operator starts at version 0.
    op.add_column(
        "operators",
        sa.Column(
            "token_version", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("operators", "token_version")
