"""Tests for retrieval.graph_builder — DB rows -> NetworkX graph."""

import time
from uuid import uuid4

import pytest

from app.extraction.db.models import (
    Chunk as ChunkRow,
    Document as DocumentRow,
    Entity,
    Relationship,
)
from app.retrieval.graph_builder import build_graph_from_db


@pytest.fixture
def seeded_graph(db_session):
    """Seed a small graph: 4 entities, 4 relationships (one duplicate pair)."""
    doc = DocumentRow(
        id=uuid4(), source_path="/tmp/gb_doc.txt", content_hash="0badcode",
        title="fixture", source_metadata={"file_type": "txt"},
    )
    db_session.add(doc)
    chunk = ChunkRow(id=uuid4(), document_id=doc.id, ordinal=0, text="c", token_count=1)
    db_session.add(chunk)

    names = ["Alice", "Bob", "Acme", "Globex"]
    entities = {n: Entity(id=uuid4(), name=n, normalized_name=n.lower(), entity_type="ORG") for n in names}
    db_session.add_all(entities.values())
    # Commit chunk + entities before relationships so the FK targets exist.
    db_session.commit()

    def rel(src, tgt, rtype):
        return Relationship(
            id=uuid4(), source_entity_id=entities[src].id, target_entity_id=entities[tgt].id,
            relation_type=rtype, source_chunk_id=chunk.id,
        )

    rels = [
        rel("Alice", "Acme", "founded"),
        rel("Bob", "Acme", "works_at"),
        rel("Acme", "Globex", "acquired"),
        # Two different relation types between the same pair must both survive.
        rel("Acme", "Globex", "partnered_with"),
    ]
    db_session.add_all(rels)
    db_session.commit()
    return entities, rels


def test_node_and_edge_counts_match_rows(seeded_graph, db_session):
    entities, rels = seeded_graph
    graph = build_graph_from_db(db_session)
    assert graph.number_of_nodes() == len(entities)
    assert graph.number_of_edges() == len(rels)


def test_parallel_relation_types_are_distinct_edges(seeded_graph, db_session):
    entities, _ = seeded_graph
    graph = build_graph_from_db(db_session)
    acme, globex = entities["Acme"].id, entities["Globex"].id
    keys = set(graph.get_edge_data(acme, globex).keys())
    assert keys == {"acquired", "partnered_with"}


def test_node_attributes_carry_name_and_type(seeded_graph, db_session):
    entities, _ = seeded_graph
    graph = build_graph_from_db(db_session)
    alice = entities["Alice"].id
    assert graph.nodes[alice]["name"] == "Alice"
    assert graph.nodes[alice]["type"] == "ORG"


def test_builds_quickly(db_session):
    """A few hundred nodes should build well under a second."""
    doc = DocumentRow(
        id=uuid4(), source_path="/tmp/gb_perf.txt", content_hash="perf1234",
        title="fixture", source_metadata={"file_type": "txt"},
    )
    db_session.add(doc)
    chunk = ChunkRow(id=uuid4(), document_id=doc.id, ordinal=0, text="c", token_count=1)
    db_session.add(chunk)
    ents = [Entity(id=uuid4(), name=f"E{i}", normalized_name=f"e{i}", entity_type="CONCEPT") for i in range(300)]
    db_session.add_all(ents)
    # Commit chunk + entities before relationships so the FK targets exist.
    db_session.commit()
    rels = [
        Relationship(id=uuid4(), source_entity_id=ents[i].id, target_entity_id=ents[i + 1].id,
                     relation_type="rel", source_chunk_id=chunk.id)
        for i in range(len(ents) - 1)
    ]
    db_session.add_all(rels)
    db_session.commit()

    start = time.perf_counter()
    graph = build_graph_from_db(db_session)
    elapsed = time.perf_counter() - start

    assert graph.number_of_nodes() == 300
    assert elapsed < 1.0
