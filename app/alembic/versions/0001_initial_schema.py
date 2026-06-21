"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documents",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("source_path", sa.String(), nullable=False, unique=True),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"])

    op.create_table(
        "chunks",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("document_id", "ordinal", name="uq_chunk_document_ordinal"),
    )

    op.create_table(
        "entities",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("normalized_name", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("normalized_name", name="uq_entities_normalized_name"),
    )
    op.create_index("ix_entities_normalized_name", "entities", ["normalized_name"])

    op.create_table(
        "relationships",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("source_entity_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("target_entity_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("relation_type", sa.String(), nullable=False),
        sa.Column("source_chunk_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["source_entity_id"], ["entities.id"]),
        sa.ForeignKeyConstraint(["target_entity_id"], ["entities.id"]),
        sa.ForeignKeyConstraint(["source_chunk_id"], ["chunks.id"]),
        sa.UniqueConstraint(
            "source_entity_id", "target_entity_id", "relation_type", name="uq_relationship"
        ),
    )

    op.create_table(
        "entity_mentions",
        sa.Column("entity_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", PG_UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"]),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"]),
        sa.PrimaryKeyConstraint("entity_id", "chunk_id"),
    )


def downgrade() -> None:
    op.drop_table("entity_mentions")
    op.drop_table("relationships")
    op.drop_table("entities")
    op.drop_table("chunks")
    op.drop_table("documents")
