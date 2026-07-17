"""Projects API routes.

POST /projects               — create a new named project
GET  /projects               — list all projects (with document count)
GET  /projects/{id}          — get a single project + its documents
POST /projects/{id}/ingest   — upload files and attach them to a project
GET  /projects/{id}/documents/{doc_id}/content — return raw text of a document
GET  /projects/{id}/graph/data — graph nodes+edges scoped to this project
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload

from app.extraction.db.session import SessionLocal, get_session
from app.extraction.db.models import (
    Project, Document, Chunk, Entity, Relationship, EntityMention
)
from app.ingestion.ingest_and_extract import ingest_and_extract

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["projects"])

ACCEPTED_SUFFIXES = {".pdf", ".txt", ".md"}


# ──────────────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    name: str


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _get_project_or_404(project_id: UUID, session: Session) -> Project:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project


def _unique_dest(tmp_dir: Path, name: str) -> Path:
    dest = tmp_dir / name
    if not dest.exists():
        return dest
    stem, suffix = Path(name).stem, Path(name).suffix
    counter = 1
    while (tmp_dir / f"{stem}-{counter}{suffix}").exists():
        counter += 1
    return tmp_dir / f"{stem}-{counter}{suffix}"


async def _run_ingestion(
    tmp_dir: Path,
    project_id: UUID,
    preassigned_ids: dict[str, UUID],
) -> None:
    """Background job: ingest files, then attach resulting Documents to the project.

    Attachment is done by looking up the preassigned IDs directly so that it
    succeeds even if extraction fails partway through (e.g. Gemini unavailable).
    """
    try:
        with SessionLocal() as session:
            try:
                await ingest_and_extract(session, tmp_dir, preassigned_ids=preassigned_ids)
            except Exception:  # noqa: BLE001
                logger.exception("ingest_and_extract failed for project %s — will still attach saved docs", project_id)

            # Attach whatever was saved (by preassigned ID) regardless of extraction outcome
            doc_ids = list(preassigned_ids.values())
            saved_docs = session.execute(
                select(Document).where(Document.id.in_(doc_ids))
            ).scalars().all()

            project = session.get(Project, project_id)
            if project and saved_docs:
                existing_ids = {d.id for d in project.documents}
                for doc in saved_docs:
                    if doc.id not in existing_ids:
                        project.documents.append(doc)
                session.commit()
                logger.info(
                    "attached %d doc(s) to project %s", len(saved_docs), project_id
                )
    except Exception:  # noqa: BLE001
        logger.exception("ingestion background task failed for project %s", project_id)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)



# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
def create_project(
    body: CreateProjectRequest,
    session: Session = Depends(get_session),
) -> dict:
    """Create a new named project."""
    project = Project(name=body.name.strip())
    session.add(project)
    session.commit()
    session.refresh(project)
    return {
        "id": str(project.id),
        "name": project.name,
        "created_at": project.created_at.isoformat(),
        "document_count": 0,
    }


@router.get("")
def list_projects(session: Session = Depends(get_session)) -> list[dict]:
    """List all projects with their document count."""
    projects = session.execute(select(Project).order_by(Project.created_at.desc())).scalars().all()
    result = []
    for p in projects:
        result.append({
            "id": str(p.id),
            "name": p.name,
            "created_at": p.created_at.isoformat(),
            "document_count": len(p.documents),
        })
    return result


@router.get("/{project_id}")
def get_project(
    project_id: UUID,
    session: Session = Depends(get_session),
) -> dict:
    """Get a single project with its document list."""
    project = session.execute(
        select(Project)
        .options(selectinload(Project.documents).selectinload(Document.chunks))
        .where(Project.id == project_id)
    ).scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    docs = []
    for doc in project.documents:
        docs.append({
            "id": str(doc.id),
            "title": doc.title or Path(doc.source_path).name,
            "source_path": doc.source_path,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "chunk_count": len(doc.chunks),
            "file_type": doc.source_metadata.get("file_type", "unknown") if doc.source_metadata else "unknown",
        })

    # Sort documents alphabetically by title
    docs.sort(key=lambda d: d["title"].lower())

    return {
        "id": str(project.id),
        "name": project.name,
        "created_at": project.created_at.isoformat(),
        "documents": docs,
    }


@router.post("/{project_id}/ingest", status_code=202)
async def ingest_to_project(
    project_id: UUID,
    files: list[UploadFile],
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    """Upload files and ingest them into the given project."""
    _get_project_or_404(project_id, session)

    tmp_dir = Path(tempfile.mkdtemp(prefix="loom_ingest_"))
    preassigned_ids: dict[str, UUID] = {}

    try:
        for file in files:
            name = Path(file.filename or "").name
            suffix = Path(name).suffix.lower()
            if suffix not in ACCEPTED_SUFFIXES:
                raise HTTPException(
                    status_code=415,
                    detail=f"Unsupported file type: {suffix} ({file.filename}). Accepted: .pdf, .txt, .md",
                )

            raw_bytes = await file.read()
            content_hash = hashlib.sha256(raw_bytes).hexdigest()
            dest = _unique_dest(tmp_dir, name)
            dest.write_bytes(raw_bytes)
            preassigned_ids.setdefault(content_hash, uuid4())
    except HTTPException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    background_tasks.add_task(_run_ingestion, tmp_dir, project_id, preassigned_ids)

    return {
        "doc_ids": [str(doc_id) for doc_id in preassigned_ids.values()],
        "project_id": str(project_id),
        "status": "processing",
    }


@router.get("/{project_id}/documents/{doc_id}/content")
def get_document_content(
    project_id: UUID,
    doc_id: UUID,
    session: Session = Depends(get_session),
) -> dict:
    """Return the reconstructed text of a document (concatenated chunks in order)."""
    project = _get_project_or_404(project_id, session)

    # Verify doc belongs to project
    doc = session.execute(
        select(Document)
        .options(selectinload(Document.chunks))
        .where(Document.id == doc_id)
    ).scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    if not any(str(d.id) == str(doc_id) for d in project.documents):
        raise HTTPException(status_code=403, detail="Document does not belong to this project")

    # Reconstruct text from chunks in ordinal order
    chunks_sorted = sorted(doc.chunks, key=lambda c: c.ordinal)
    full_text = "\n\n".join(c.text for c in chunks_sorted)

    return {
        "id": str(doc.id),
        "title": doc.title or Path(doc.source_path).name,
        "file_type": doc.source_metadata.get("file_type", "unknown") if doc.source_metadata else "unknown",
        "text": full_text,
        "chunk_count": len(doc.chunks),
    }


@router.get("/{project_id}/graph/data")
def get_project_graph(
    project_id: UUID,
    session: Session = Depends(get_session),
) -> dict:
    """Build the knowledge graph scoped to documents in this project."""
    project = session.execute(
        select(Project)
        .options(selectinload(Project.documents))
        .where(Project.id == project_id)
    ).scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    doc_ids = {doc.id for doc in project.documents}

    if not doc_ids:
        return {"nodes": [], "edges": []}

    # Fetch chunks belonging to this project's documents
    chunks = session.execute(
        select(Chunk).where(Chunk.document_id.in_(doc_ids))
    ).scalars().all()
    chunk_ids = {c.id for c in chunks}

    # Entity mentions scoped to these chunks
    mentions_rows = session.execute(
        select(EntityMention).where(EntityMention.chunk_id.in_(chunk_ids))
    ).scalars().all()

    entity_ids = {m.entity_id for m in mentions_rows}

    # Entities
    entities = session.execute(
        select(Entity).where(Entity.id.in_(entity_ids))
    ).scalars().all()

    # Relationships between entities in this project scope
    relationships = session.execute(
        select(Relationship).where(
            Relationship.source_entity_id.in_(entity_ids),
            Relationship.target_entity_id.in_(entity_ids),
        )
    ).scalars().all()

    # Build distinct doc→entity mention links
    doc_entity_pairs: set[tuple[UUID, UUID]] = set()
    chunk_to_doc = {c.id: c.document_id for c in chunks}
    for m in mentions_rows:
        doc_id = chunk_to_doc.get(m.chunk_id)
        if doc_id:
            doc_entity_pairs.add((doc_id, m.entity_id))

    # Format nodes
    nodes = []
    for doc in project.documents:
        nodes.append({
            "id": f"doc-{doc.id}",
            "label": doc.title or Path(doc.source_path).name,
            "type": "document",
            "doc_id": str(doc.id),
            "metadata": {
                "source_path": doc.source_path,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "file_type": doc.source_metadata.get("file_type", "unknown") if doc.source_metadata else "unknown",
            },
        })

    for entity in entities:
        nodes.append({
            "id": f"entity-{entity.id}",
            "label": entity.name,
            "type": "entity",
            "entity_type": entity.entity_type,
        })

    # Format edges
    edges = []
    for rel in relationships:
        edges.append({
            "id": f"rel-{rel.id}",
            "source": f"entity-{rel.source_entity_id}",
            "target": f"entity-{rel.target_entity_id}",
            "label": rel.relation_type,
            "type": "relationship",
        })

    for doc_id, entity_id in doc_entity_pairs:
        edges.append({
            "id": f"mention-{doc_id}-{entity_id}",
            "source": f"doc-{doc_id}",
            "target": f"entity-{entity_id}",
            "label": "mentions",
            "type": "mention",
        })

    return {"nodes": nodes, "edges": edges}
