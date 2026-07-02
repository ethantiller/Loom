"""Tests for retrieval.vector_search.

Embeddings are hand-crafted orthogonal unit vectors so expected cosine
ranking is exact and requires no ML model.
"""

import numpy as np
import pytest
from uuid import uuid4
from sqlalchemy import text

from app.extraction.db.models import Chunk as ChunkRow, Document as DocumentRow
from app.retrieval.vector_search import similarity_search


DIM = 768


def _unit(axis: int) -> list[float]:
    """768-dim unit vector pointing along a single axis."""
    v = [0.0] * DIM
    v[axis] = 1.0
    return v


@pytest.fixture
def seeded_chunks(db_session):
    """Three chunks whose embeddings are axis-aligned unit vectors e0, e1, e2."""
    doc = DocumentRow(
        id=uuid4(),
        source_path="/tmp/fixture_doc.txt",
        content_hash="deadbeef",
        title="fixture",
        source_metadata={"file_type": "txt"},
    )
    db_session.add(doc)

    chunks = [
        ChunkRow(id=uuid4(), document_id=doc.id, ordinal=i,
                 text=f"chunk {i}", token_count=2, embedding=_unit(i))
        for i in range(3)
    ]
    db_session.add_all(chunks)
    db_session.commit()
    return chunks


def test_returns_nearest_neighbor_first(seeded_chunks, db_session):
    # Query almost exactly aligned with axis 1 → chunk 1 should be closest.
    q = np.array(_unit(1), dtype=np.float32)
    results = similarity_search(db_session, q, k=3)

    assert len(results) == 3
    assert results[0].ordinal == 1


def test_ranking_order_by_cosine_distance(seeded_chunks, db_session):
    # Query = normalize([0.9, 0.4, 0.1, 0, …]) → cosine similarity decreases
    # with axis index, so expected order is chunk 0 > chunk 1 > chunk 2.
    raw = np.zeros(DIM, dtype=np.float32)
    raw[0], raw[1], raw[2] = 0.9, 0.4, 0.1
    q = raw / np.linalg.norm(raw)

    results = similarity_search(db_session, q, k=3)

    assert [r.ordinal for r in results] == [0, 1, 2]


def test_k_limits_results(seeded_chunks, db_session):
    q = np.array(_unit(0), dtype=np.float32)
    results = similarity_search(db_session, q, k=2)
    assert len(results) == 2


def test_hnsw_index_exists(db_engine):
    with db_engine.connect() as conn:
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx "
            "ON chunks USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        ))
        conn.commit()

        row = conn.execute(text(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'chunks' AND indexname = 'chunks_embedding_hnsw_idx'"
        )).fetchone()

        conn.execute(text("DROP INDEX IF EXISTS chunks_embedding_hnsw_idx"))
        conn.commit()

    assert row is not None, "HNSW index was not found in pg_indexes"
