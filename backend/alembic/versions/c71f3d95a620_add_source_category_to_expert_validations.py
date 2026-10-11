"""Add source provenance to expert validations.

Revision ID: c71f3d95a620
Revises: eb9b2b079882
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c71f3d95a620"
down_revision: Union[str, None] = "eb9b2b079882"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "expert_validations",
        sa.Column("source_category", sa.String(length=80), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("expert_validations", "source_category")
