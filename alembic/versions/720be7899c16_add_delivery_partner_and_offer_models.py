
"""add delivery partner and offer models

Revision ID: 720be7899c16
Revises: c01f08a88414
Create Date: 2026-10-23 10:54:46.719528
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "720be7899c16"
down_revision: Union[str, Sequence[str], None] = "c01f08a88414"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    The delivery tables and their expected indexes already exist
    in the database from the partially completed migration.
    Keep them and allow Alembic to record this revision.
    """
    pass


def downgrade() -> None:
    """
    Remove the delivery tables if this revision is intentionally
    rolled back. Preserve order_status_history.
    """
    op.drop_index(
        op.f("ix_delivery_offers_partner_id"),
        table_name="delivery_offers",
    )
    op.drop_index(
        op.f("ix_delivery_offers_order_id"),
        table_name="delivery_offers",
    )
    op.drop_index(
        op.f("ix_delivery_offers_id"),
        table_name="delivery_offers",
    )
    op.drop_table("delivery_offers")

    op.drop_index(
        op.f("ix_delivery_partners_user_id"),
        table_name="delivery_partners",
    )
    op.drop_index(
        op.f("ix_delivery_partners_id"),
        table_name="delivery_partners",
    )
    op.drop_table("delivery_partners")
