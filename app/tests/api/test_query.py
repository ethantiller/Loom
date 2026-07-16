"""Tests for POST /query.

The genai client is a scripted MagicMock (injected via `_build_client`) and
`embed_query` is monkeypatched for deterministic vector ranking, while the
retrieval tools run for real against a seeded Postgres DB. The get_session
dependency is overridden to reuse the test's transactional session.
"""

from unittest.mock import MagicMock
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.extraction.db.models import (
    Chunk as ChunkRow,
    Document as DocumentRow,
    Entity,
    EntityMention,
    Relationship,
)
from app.extraction.db.session import get_session
from app.main import app

DIM = 768


def _unit(axis: int) -> list[float]:
    v = [0.0] * DIM
    v[axis] = 1.0
    return v


def _fc(name: str, args: dict):
    call = MagicMock()
    call.name = name
    call.args = args
    resp = MagicMock()
    resp.function_calls = [call]
    return resp


@pytest.fixture
def seeded(db_session, monkeypatch):
    """One doc, two chunks, and an Ada→Babbage relationship (mirrors test_agent)."""
    monkeypatch.setattr("app.retrieval.agent.embed_query",
                        lambda _q: np.array(_unit(0), dtype=np.float32))

    doc = DocumentRow(id=uuid4(), source_path=f"/tmp/query_{uuid4().hex}.txt",
                      content_hash="queryfx", title="fixture",
                      source_metadata={"file_type": "txt"})
    db_session.add(doc)
    chunks = [
        ChunkRow(id=uuid4(), document_id=doc.id, ordinal=i, text=f"chunk {i}",
                 token_count=5, embedding=_unit(i))
        for i in range(2)
    ]
    db_session.add_all(chunks)

    ada = Entity(id=uuid4(), name="Ada", normalized_name="ada", entity_type="PERSON")
    babbage = Entity(id=uuid4(), name="Babbage", normalized_name="babbage", entity_type="PERSON")
    db_session.add_all([ada, babbage])
    db_session.add(EntityMention(entity_id=ada.id, chunk_id=chunks[0].id))
    db_session.commit()

    db_session.add(Relationship(id=uuid4(), source_entity_id=ada.id,
                                target_entity_id=babbage.id, relation_type="collaborated_with",
                                source_chunk_id=chunks[0].id))
    db_session.commit()
    return {"chunks": chunks, "ada": ada, "babbage": babbage}


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_multi_hop_query_returns_answer_with_citations(seeded, client, monkeypatch):
    babbage = seeded["babbage"]
    scripted = MagicMock()
    scripted.models.generate_content.side_effect = [
        _fc("vector_search", {"query": "ada collaborators"}),
        _fc("expand_graph", {"seed_entity_names": ["Ada"]}),
        _fc("finalize_answer",
            {"answer": f"Ada collaborated with Babbage [entity:{babbage.id}]."}),
    ]
    monkeypatch.setattr("app.retrieval.agent._build_client", lambda _c: scripted)

    response = client.post("/query", json={"question": "Who did Ada collaborate with?"})

    assert response.status_code == 200
    body = response.json()
    assert "Babbage" in body["answer"]
    assert body["citations"]  # non-empty
    assert body["citations"][0]["type"] == "entity"
    assert body["citations"][0]["id"] == str(babbage.id)
    assert body["steps"] == 3
    assert body["latency_ms"] > 0
