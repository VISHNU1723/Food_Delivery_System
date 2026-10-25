
"""add ratings table and restaurant average rating

Revision ID: 057da0adba59
Revises: b8d93641ca77
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "057da0adba59"
down_revision: Union[str, Sequence[str], None] = "b8d93641ca77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # The ratings table already exists in the database.
    # Add only the missing restaurant average_rating column.
    op.add_column(
        "restaurants",
        sa.Column(
            "average_rating",
            sa.Float(),
            nullable=False,
            server_default="0.0",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_column("restaurants", "average_rating")
