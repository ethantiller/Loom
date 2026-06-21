"""resize embedding vector from 384 to 768

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-20
"""
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "chunks",
        "embedding",
        type_=Vector(768),
        postgresql_using="embedding::vector(768)",
    )


def downgrade() -> None:
    op.alter_column(
        "chunks",
        "embedding",
        type_=Vector(384),
        postgresql_using="embedding::vector(384)",
    )
