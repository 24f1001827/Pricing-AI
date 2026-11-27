"""Baseline production schema

Revision ID: 0001_baseline_schema
Revises:
Create Date: 2026-11-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from core.database import ensure_schema
from core.database_models import Base

revision: str = "0001_baseline_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    ensure_schema(bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
