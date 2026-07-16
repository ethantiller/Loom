"""Tests for retrieval.agent — the bounded ReAct controller.

The genai client is mocked with a scripted sequence of tool-call / text
responses, while the tools run for real against a seeded DB (embed_query is
monkeypatched so vector ranking is deterministic without loading a model).
"""

from unittest.mock import MagicMock
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
from app.retrieval.agent import RetrievalAgent

DIM = 768


def _unit(axis: int) -> list[float]:
    v = [0.0] * DIM
    v[axis] = 1.0
    return v


def _fc(name: str, args: dict):
    """A response whose model turn is a single function call."""
    call = MagicMock()
    call.name = name
    call.args = args
    resp = MagicMock()
    resp.function_calls = [call]
    return resp


def _text(text: str):
    """A response with no tool call (plain text)."""
    resp = MagicMock()
    resp.function_calls = []
    resp.text = text
    return resp


def _client(responses):
    client = MagicMock()
    client.models.generate_content.side_effect = responses
    return client


class _Settings:
    def __init__(self, retrieval_max_steps: int):
        self.retrieval_max_steps = retrieval_max_steps


@pytest.fixture
def seeded(db_session, monkeypatch):
    """One doc, two chunks, and an Ada→Babbage relationship. Query maps to chunk0."""
    monkeypatch.setattr("app.retrieval.agent.embed_query",
                        lambda _q: np.array(_unit(0), dtype=np.float32))

    doc = DocumentRow(id=uuid4(), source_path=f"/tmp/agent_{uuid4().hex}.txt",
                      content_hash="agentfx", title="fixture",
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
    # Commit chunk + entities before relationships so the FK targets exist.
    db_session.commit()

    db_session.add(Relationship(id=uuid4(), source_entity_id=ada.id,
                                target_entity_id=babbage.id, relation_type="collaborated_with",
                                source_chunk_id=chunks[0].id))
    db_session.commit()
    return {"chunks": chunks, "ada": ada, "babbage": babbage}


def test_single_hop_finalizes_within_two_steps(seeded, db_session):
    chunk0 = seeded["chunks"][0]
    client = _client([
        _fc("vector_search", {"query": "who is ada"}),
        _fc("finalize_answer", {"answer": f"Ada is a person [chunk:{chunk0.id}].",
                                 "citations": [f"chunk:{chunk0.id}"]}),
    ])

    result = RetrievalAgent(db_session, client=client).run("Who is Ada?")

    names = [s["name"] for s in result.steps]
    assert names == ["vector_search", "finalize_answer"]
    assert "expand_graph" not in names
    assert result.truncated is False
    assert result.answer
    assert any(c.id == str(chunk0.id) for c in result.citations)


def test_multi_hop_expands_graph_before_finalizing(seeded, db_session):
    babbage = seeded["babbage"]
    client = _client([
        _fc("vector_search", {"query": "ada collaborators"}),
        _fc("expand_graph", {"seed_entity_names": ["Ada"]}),
        _fc("finalize_answer", {"answer": f"Ada collaborated with Babbage [entity:{babbage.id}]."}),
    ])

    result = RetrievalAgent(db_session, client=client).run("Who did Ada collaborate with?")

    names = [s["name"] for s in result.steps]
    assert "expand_graph" in names
    assert names.index("expand_graph") < names.index("finalize_answer")
    assert result.truncated is False
    assert str(babbage.id) in result.context.entities
    assert any(c.id == str(babbage.id) for c in result.citations)


def test_loop_stops_at_max_steps_without_finalize(seeded, db_session, monkeypatch):
    monkeypatch.setattr("app.retrieval.agent.get_settings", lambda: _Settings(3))
    client = _client([
        _fc("vector_search", {"query": "q1"}),
        _fc("vector_search", {"query": "q2"}),
        _fc("vector_search", {"query": "q3"}),
        _text("Forced answer from accumulated context."),  # forced final generation
    ])

    result = RetrievalAgent(db_session, client=client).run("Never answered directly")

    assert len(result.steps) == 3  # stopped at exactly max_steps
    assert all(s["name"] == "vector_search" for s in result.steps)
    assert result.truncated is True
    assert result.answer == "Forced answer from accumulated context."
    assert client.models.generate_content.call_count == 4  # 3 loop + 1 forced
