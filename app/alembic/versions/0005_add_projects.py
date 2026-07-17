"""add projects and project_documents tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "project_documents",
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("project_documents")
    op.drop_table("projects")
