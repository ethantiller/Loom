"""Tests for retrieval.graph_traversal — seeds, subgraph expansion, rendering."""

from uuid import uuid4

import networkx as nx
import pytest

from app.extraction.db.models import (
    Chunk as ChunkRow,
    Document as DocumentRow,
    Entity,
    EntityMention,
)
from app.ingestion.chunker import _get_tokenizer
from app.retrieval.graph_traversal import (
    expand_subgraph,
    find_seed_entities,
    subgraph_to_context,
)


def test_find_seed_entities_returns_mentioned_entity(db_session):
    doc = DocumentRow(
        id=uuid4(), source_path="/tmp/gt_doc.txt", content_hash="seed1234",
        title="fixture", source_metadata={"file_type": "txt"},
    )
    db_session.add(doc)
    chunk = ChunkRow(id=uuid4(), document_id=doc.id, ordinal=0, text="c", token_count=1)
    entity_x = Entity(id=uuid4(), name="X", normalized_name="x", entity_type="CONCEPT")
    other = Entity(id=uuid4(), name="Y", normalized_name="y", entity_type="CONCEPT")
    db_session.add_all([chunk, entity_x, other])
    db_session.add(EntityMention(entity_id=entity_x.id, chunk_id=chunk.id))
    db_session.commit()

    seeds = find_seed_entities(chunk.id, db_session)
    assert seeds == [entity_x.id]


def _path_graph_5():
    """n0 → n1 → n2 → n3 → n4, each node named after its index."""
    nodes = [uuid4() for _ in range(5)]
    graph = nx.MultiDiGraph()
    for i, n in enumerate(nodes):
        graph.add_node(n, name=f"n{i}", type="CONCEPT")
    for i in range(4):
        graph.add_edge(nodes[i], nodes[i + 1], key="next", relation="next", chunk_id=uuid4())
    return graph, nodes


def test_expand_subgraph_respects_hop_radius():
    graph, nodes = _path_graph_5()
    sub = expand_subgraph(graph, [nodes[0]], n_hops=2)
    # Within 2 undirected hops of n0: n0, n1, n2 — but not n3 or n4.
    assert set(sub.nodes) == {nodes[0], nodes[1], nodes[2]}


def test_expand_subgraph_skips_unknown_seed():
    graph, nodes = _path_graph_5()
    sub = expand_subgraph(graph, [uuid4()], n_hops=2)
    assert sub.number_of_nodes() == 0


def test_subgraph_to_context_renders_unique_triples():
    graph, nodes = _path_graph_5()
    text = subgraph_to_context(graph)
    lines = text.split("\n")

    assert lines == ["n0 → next → n1", "n1 → next → n2", "n2 → next → n3", "n3 → next → n4"]
    assert len(lines) == len(set(lines))  # no duplicates


def test_subgraph_to_context_respects_token_budget():
    graph, nodes = _path_graph_5()
    full = subgraph_to_context(graph, token_budget=10_000).split("\n")
    assert len(full) == 4  # all edges fit under a generous budget

    # A budget matching exactly the first two lines truncates to those two.
    two = "\n".join(full[:2])
    budget = len(_get_tokenizer()(two, add_special_tokens=False)["input_ids"])
    assert subgraph_to_context(graph, token_budget=budget) == two
