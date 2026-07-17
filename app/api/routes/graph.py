"""Endpoints for retrieving document list and knowledge graph data.

Allows the UI to display all ingested files and visualize the node-link graph of
documents, extracted entities, and relations.
"""

from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.extraction.db.session import get_session
from app.extraction.db.models import Document, Chunk, Entity, Relationship, EntityMention

router = APIRouter()


@router.get("/documents")
def list_documents(session: Session = Depends(get_session)) -> list[dict]:
    """Retrieve all ingested documents, including their chunk count."""
    stmt = (
        select(
            Document.id,
            Document.title,
            Document.source_path,
            Document.created_at,
            func.count(Chunk.id).label("chunk_count")
        )
        .outerjoin(Chunk, Document.id == Chunk.document_id)
        .group_by(Document.id)
        .order_by(Document.created_at.desc())
    )
    results = session.execute(stmt).all()

    return [
        {
            "id": str(r.id),
            "title": r.title or Path(r.source_path).name,
            "source_path": r.source_path,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "chunk_count": r.chunk_count,
        }
        for r in results
    ]


@router.get("/graph/data")
def get_graph_data(session: Session = Depends(get_session)) -> dict:
    """Retrieve the unified graph structure containing documents, entities, and edges."""
    # 1. Fetch all documents
    docs = session.execute(select(Document)).scalars().all()

    # 2. Fetch all entities
    entities = session.execute(select(Entity)).scalars().all()

    # 3. Fetch all entity-entity relationships
    relationships = session.execute(select(Relationship)).scalars().all()

    # 4. Fetch document-entity mentions (distinct document_id -> entity_id links via chunks)
    mentions_stmt = (
        select(Chunk.document_id, EntityMention.entity_id)
        .join(EntityMention, Chunk.id == EntityMention.chunk_id)
        .distinct()
    )
    mentions = session.execute(mentions_stmt).all()

    # Format nodes
    nodes = []
    for doc in docs:
        nodes.append({
            "id": f"doc-{doc.id}",
            "label": doc.title or Path(doc.source_path).name,
            "type": "document",
            "metadata": {
                "source_path": doc.source_path,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
        })

    for entity in entities:
        nodes.append({
            "id": f"entity-{entity.id}",
            "label": entity.name,
            "type": "entity",
            "entity_type": entity.entity_type
        })

    # Format edges
    edges = []
    for rel in relationships:
        edges.append({
            "id": f"rel-{rel.id}",
            "source": f"entity-{rel.source_entity_id}",
            "target": f"entity-{rel.target_entity_id}",
            "label": rel.relation_type,
            "type": "relationship"
        })

    for doc_id, entity_id in mentions:
        edges.append({
            "id": f"mention-{doc_id}-{entity_id}",
            "source": f"doc-{doc_id}",
            "target": f"entity-{entity_id}",
            "label": "mentions",
            "type": "mention"
        })

    return {
        "nodes": nodes,
        "edges": edges
    }
