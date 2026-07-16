"""Tests for retrieval.hybrid — vector + graph composition and token budgeting.

Chunk embeddings are hand-crafted axis-aligned unit vectors and the query
embedding is monkeypatched, so cosine ranking is exact and no ML model is
loaded. ``embed_query`` is patched at its import site in ``app.retrieval.hybrid``.
"""

from uuid import uuid4

import numpy as np
import pytest

from app.extraction.db.models import (
    Chunk as ChunkRow,
    Document as DocumentRow,
    Entity,
    EntityMention,
    Relationship,
)
from app.ingestion.chunker import count_tokens
from app.retrieval.hybrid import HybridRetriever

DIM = 768


def _unit(axis: int) -> list[float]:
    v = [0.0] * DIM
    v[axis] = 1.0
    return v


def _patch_query(monkeypatch, vector: list[float]) -> None:
    arr = np.array(vector, dtype=np.float32)
    monkeypatch.setattr("app.retrieval.hybrid.embed_query", lambda _query: arr)


def _make_doc(db_session) -> DocumentRow:
    doc = DocumentRow(
        id=uuid4(),
        source_path=f"/tmp/hybrid_{uuid4().hex}.txt",
        content_hash="hybridfx",
        title="fixture",
        source_metadata={"file_type": "txt"},
    )
    db_session.add(doc)
    return doc


class _Settings:
    """Minimal stand-in for Settings, exposing only what HybridRetriever reads."""

    def __init__(self, max_context_tokens: int):
        self.max_context_tokens = max_context_tokens


def _patch_budget(monkeypatch, budget: int) -> None:
    monkeypatch.setattr("app.retrieval.hybrid.get_settings", lambda: _Settings(budget))


def test_multi_hop_fact_from_chunk_outside_top5(db_session, monkeypatch):
    """A graph fact surfaces even though its source chunk is not a top-5 hit."""
    doc = _make_doc(db_session)

    # Six chunks along axes 0..5; query weights decrease with axis so the strict
    # cosine order is chunk0 > chunk1 > ... > chunk5. With k=5, chunk5 is excluded.
    chunks = [
        ChunkRow(id=uuid4(), document_id=doc.id, ordinal=i, text=f"chunk {i}",
                 token_count=5, embedding=_unit(i))
        for i in range(6)
    ]
    db_session.add_all(chunks)

    entity_a = Entity(id=uuid4(), name="Ada", normalized_name="ada", entity_type="PERSON")
    entity_b = Entity(id=uuid4(), name="Babbage", normalized_name="babbage", entity_type="PERSON")
    db_session.add_all([entity_a, entity_b])

    # Ada is mentioned in the top-ranked chunk (retrieved); Babbage only in chunk5
    # (NOT retrieved). The relationship is sourced from chunk5.
    db_session.add(EntityMention(entity_id=entity_a.id, chunk_id=chunks[0].id))
    db_session.add(EntityMention(entity_id=entity_b.id, chunk_id=chunks[5].id))
    # Commit chunk + entities before relationships so the FK targets exist
    # (Relationship has no ORM relationship() mapping to order the insert).
    db_session.commit()

    db_session.add(Relationship(
        id=uuid4(), source_entity_id=entity_a.id, target_entity_id=entity_b.id,
        relation_type="collaborated_with", source_chunk_id=chunks[5].id,
    ))
    db_session.commit()

    _patch_query(monkeypatch, [6 - i if i < 6 else 0 for i in range(DIM)])

    ctx = HybridRetriever(db_session).retrieve("who collaborated?", k=5)

    retrieved_ids = {c.id for c in ctx.chunks}
    assert chunks[5].id not in retrieved_ids  # the fact's source chunk was NOT retrieved
    assert "Ada → collaborated_with → Babbage" in ctx.graph_facts
    assert str(entity_b.id) in ctx.entities  # entity id exposed for citation


def test_total_tokens_within_budget_when_chunks_overflow(db_session, monkeypatch):
    """Oversized chunk text alone forces chunk dropping; total stays under budget."""
    doc = _make_doc(db_session)
    chunks = [
        ChunkRow(id=uuid4(), document_id=doc.id, ordinal=i, text=f"chunk {i}",
                 token_count=1000, embedding=_unit(i))
        for i in range(5)
    ]
    db_session.add_all(chunks)
    db_session.commit()

    _patch_query(monkeypatch, _unit(0))
    _patch_budget(monkeypatch, 2500)

    ctx = HybridRetriever(db_session).retrieve("q", k=5)

    assert ctx.total_tokens <= 2500
    assert ctx.graph_facts == ""          # no room left for supplementary facts
    assert len(ctx.chunks) == 2           # 2 * 1000 fits, 3 * 1000 would not


def test_graph_facts_trimmed_before_chunks(db_session, monkeypatch):
    """When context overflows, graph facts are trimmed but all chunks are kept."""
    doc = _make_doc(db_session)
    chunks = [
        ChunkRow(id=uuid4(), document_id=doc.id, ordinal=i, text=f"chunk {i}",
                 token_count=5, embedding=_unit(i))
        for i in range(2)
    ]
    db_session.add_all(chunks)

    # A star of relationships off a mentioned entity produces many triples.
    hub = Entity(id=uuid4(), name="Hub", normalized_name="hub", entity_type="CONCEPT")
    db_session.add(hub)
    db_session.add(EntityMention(entity_id=hub.id, chunk_id=chunks[0].id))
    spokes = [
        Entity(id=uuid4(), name=f"Spoke{i}", normalized_name=f"spoke{i}", entity_type="CONCEPT")
        for i in range(30)
    ]
    db_session.add_all(spokes)
    # Commit chunk + entities before relationships so the FK targets exist.
    db_session.commit()

    db_session.add_all([
        Relationship(id=uuid4(), source_entity_id=hub.id, target_entity_id=spoke.id,
                     relation_type="relates_to", source_chunk_id=chunks[0].id)
        for spoke in spokes
    ])
    db_session.commit()

    _patch_query(monkeypatch, _unit(0))
    _patch_budget(monkeypatch, 40)

    ctx = HybridRetriever(db_session).retrieve("q", k=2)

    assert ctx.total_tokens <= 40
    assert len(ctx.chunks) == 2                      # chunks preserved
    assert ctx.graph_facts != ""                     # some facts survive
    assert count_tokens(ctx.graph_facts) <= 40 - 10  # trimmed to remaining budget
    assert ctx.graph_facts.count("\n") + 1 < 30      # not all 30 triples fit → trimmed
