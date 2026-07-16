"""Tests for extraction.graph_store — idempotent graph persistence."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.extraction.db.models import (
    Chunk as ChunkRow,
    Document as DocumentRow,
    Entity,
    EntityMention,
    Relationship,
)
from app.extraction.graph_store import (
    store_extraction_results,
    upsert_entity,
    upsert_relationship,
)
from app.extraction.schemas import ExtractedEntity, ExtractedRelationship, ExtractionResult


@pytest.fixture
def document(db_session):
    doc = DocumentRow(
        id=uuid4(),
        source_path="/tmp/graph_store_doc.txt",
        content_hash="cafef00d",
        title="fixture",
        source_metadata={"file_type": "txt"},
    )
    db_session.add(doc)
    db_session.commit()
    return doc


def _make_chunk(db_session, document, ordinal: int) -> ChunkRow:
    chunk = ChunkRow(
        id=uuid4(),
        document_id=document.id,
        ordinal=ordinal,
        text=f"chunk {ordinal}",
        token_count=2,
    )
    db_session.add(chunk)
    db_session.commit()
    return chunk


def test_entity_normalization_collapses_variants(db_session):
    # AC1: "OpenAI" then "  open ai " (whitespace + case) -> exactly one row.
    first = upsert_entity(db_session, "OpenAI", "ORG")
    second = upsert_entity(db_session, "  open ai ", "ORG")
    db_session.commit()

    assert first.id == second.id
    count = db_session.execute(select(func.count()).select_from(Entity)).scalar_one()
    assert count == 1


def test_relationship_upsert_is_idempotent(db_session, document):
    chunk = _make_chunk(db_session, document, 0)
    a = upsert_entity(db_session, "Alice", "PERSON")
    b = upsert_entity(db_session, "Acme", "ORG")
    db_session.commit()

    # AC2: same (source, target, relation) triple twice -> one row.
    upsert_relationship(db_session, a.id, b.id, "founded", chunk.id)
    upsert_relationship(db_session, a.id, b.id, "founded", chunk.id)
    db_session.commit()

    count = db_session.execute(select(func.count()).select_from(Relationship)).scalar_one()
    assert count == 1


def test_entity_mentions_across_chunks_are_all_retained(db_session, document):
    # AC3: an entity mentioned in 3 chunks retains all 3 citations.
    chunks = [_make_chunk(db_session, document, i) for i in range(3)]
    result = ExtractionResult(
        entities=[ExtractedEntity(name="OpenAI", type="ORG")],
        relationships=[],
    )
    store_extraction_results(db_session, [(chunk, result) for chunk in chunks])

    entity = db_session.execute(select(Entity)).scalar_one()
    mention_chunk_ids = set(
        db_session.execute(
            select(EntityMention.chunk_id).where(EntityMention.entity_id == entity.id)
        ).scalars()
    )
    assert mention_chunk_ids == {chunk.id for chunk in chunks}


def test_store_extraction_results_persists_full_graph(db_session, document):
    chunk = _make_chunk(db_session, document, 0)
    result = ExtractionResult(
        entities=[
            ExtractedEntity(name="Sam Altman", type="PERSON"),
            ExtractedEntity(name="OpenAI", type="ORG"),
        ],
        relationships=[
            ExtractedRelationship(source="Sam Altman", target="OpenAI", relation="founded"),
            # Dangling endpoint ("Microsoft" was never extracted) must be skipped, not raised.
            ExtractedRelationship(source="OpenAI", target="Microsoft", relation="partnered_with"),
        ],
    )
    store_extraction_results(db_session, [(chunk, result)])

    entities = db_session.execute(select(Entity)).scalars().all()
    assert {e.name for e in entities} == {"Sam Altman", "OpenAI"}

    rels = db_session.execute(select(Relationship)).scalars().all()
    assert len(rels) == 1
    assert rels[0].relation_type == "founded"
    assert rels[0].source_chunk_id == chunk.id

    mention_count = db_session.execute(select(func.count()).select_from(EntityMention)).scalar_one()
    assert mention_count == 2
