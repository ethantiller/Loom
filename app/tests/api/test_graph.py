"""Tests for graph endpoints GET /documents and GET /graph/data."""

import pytest
from fastapi.testclient import TestClient
from uuid import uuid4

from app.extraction.db.models import Document, Chunk, Entity, Relationship, EntityMention, project_document
from app.main import app


def test_list_documents_empty(db_session):
    # Clear any pre-existing database records to isolate the test
    db_session.execute(project_document.delete())
    db_session.query(Document).delete()
    db_session.commit()
    
    client = TestClient(app)
    response = client.get("/documents")
    assert response.status_code == 200
    assert response.json() == []


def test_list_documents_with_data(db_session):
    client = TestClient(app)

    # Insert test document
    doc = Document(
        id=uuid4(),
        source_path="test_doc.txt",
        content_hash="hash123",
        title="Test Doc Title"
    )
    db_session.add(doc)
    db_session.commit()

    # Add chunks
    chunk1 = Chunk(
        id=uuid4(),
        document_id=doc.id,
        ordinal=0,
        text="This is chunk 1.",
        token_count=5
    )
    chunk2 = Chunk(
        id=uuid4(),
        document_id=doc.id,
        ordinal=1,
        text="This is chunk 2.",
        token_count=5
    )
    db_session.add_all([chunk1, chunk2])
    db_session.commit()

    response = client.get("/documents")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "Test Doc Title"
    assert data[0]["chunk_count"] == 2


def test_get_graph_data(db_session):
    client = TestClient(app)

    # 1. Insert documents
    doc = Document(
        id=uuid4(),
        source_path="loom_manual.pdf",
        content_hash="hash_pdf",
        title="Loom Manual"
    )
    db_session.add(doc)
    db_session.commit()

    chunk = Chunk(
        id=uuid4(),
        document_id=doc.id,
        ordinal=0,
        text="Antigravity is designed by Google Deepmind.",
        token_count=7
    )
    db_session.add(chunk)
    db_session.commit()

    # 2. Insert entities
    entity1 = Entity(
        id=uuid4(),
        name="Antigravity",
        normalized_name="antigravity",
        entity_type="AI_AGENT"
    )
    entity2 = Entity(
        id=uuid4(),
        name="Google Deepmind",
        normalized_name="google deepmind",
        entity_type="ORGANIZATION"
    )
    db_session.add_all([entity1, entity2])
    db_session.commit()

    # 3. Add Entity mentions
    mention1 = EntityMention(entity_id=entity1.id, chunk_id=chunk.id)
    mention2 = EntityMention(entity_id=entity2.id, chunk_id=chunk.id)
    db_session.add_all([mention1, mention2])
    db_session.commit()

    # 4. Add Entity relationships
    rel = Relationship(
        id=uuid4(),
        source_entity_id=entity1.id,
        target_entity_id=entity2.id,
        relation_type="CREATED_BY",
        source_chunk_id=chunk.id
    )
    db_session.add(rel)
    db_session.commit()

    # Query graph data
    response = client.get("/graph/data")
    assert response.status_code == 200
    graph_data = response.json()

    # Assert nodes
    nodes = graph_data["nodes"]
    assert len(nodes) == 3  # 1 document + 2 entities
    
    doc_node = next(n for n in nodes if n["type"] == "document")
    assert doc_node["label"] == "Loom Manual"
    assert doc_node["id"] == f"doc-{doc.id}"

    entity_nodes = [n for n in nodes if n["type"] == "entity"]
    assert len(entity_nodes) == 2
    assert any(e["label"] == "Antigravity" and e["entity_type"] == "AI_AGENT" for e in entity_nodes)
    assert any(e["label"] == "Google Deepmind" and e["entity_type"] == "ORGANIZATION" for e in entity_nodes)

    # Assert edges
    edges = graph_data["edges"]
    assert len(edges) == 3  # 1 relationship + 2 mentions

    relationship_edges = [e for e in edges if e["type"] == "relationship"]
    assert len(relationship_edges) == 1
    assert relationship_edges[0]["source"] == f"entity-{entity1.id}"
    assert relationship_edges[0]["target"] == f"entity-{entity2.id}"
    assert relationship_edges[0]["label"] == "CREATED_BY"

    mention_edges = [e for e in edges if e["type"] == "mention"]
    assert len(mention_edges) == 2
    assert any(m["source"] == f"doc-{doc.id}" and m["target"] == f"entity-{entity1.id}" for m in mention_edges)
    assert any(m["source"] == f"doc-{doc.id}" and m["target"] == f"entity-{entity2.id}" for m in mention_edges)
