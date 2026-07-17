"""POST /ingest — accept uploads and ingest them into the knowledge graph.

Validates file types up front, stages accepted uploads to a temp directory, and
runs the (blocking, minutes-long) ingest → extract → store pipeline in a
``BackgroundTasks`` job so the request returns ``202 Accepted`` immediately. The
``doc_ids`` are minted synchronously and threaded into the pipeline so the client
can correlate the response with the rows that will land in the DB.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile

from app.extraction.db.session import SessionLocal
from app.ingestion.ingest_and_extract import ingest_and_extract

logger = logging.getLogger(__name__)

router = APIRouter()

ACCEPTED_SUFFIXES = {".pdf", ".txt", ".md"}


def _unique_dest(tmp_dir: Path, name: str) -> Path:
    """A path under ``tmp_dir`` for ``name``, appending -1/-2/... on collision."""
    dest = tmp_dir / name
    if not dest.exists():
        return dest
    stem, suffix = Path(name).stem, Path(name).suffix
    counter = 1
    while (tmp_dir / f"{stem}-{counter}{suffix}").exists():
        counter += 1
    return tmp_dir / f"{stem}-{counter}{suffix}"


async def _run_ingestion(tmp_dir: Path, preassigned_ids: dict[str, UUID]) -> None:
    """Background job: ingest the staged files, then clean up the temp dir.

    Opens its own session because the request-scoped session is already closed by
    the time a background task runs.
    """
    try:
        with SessionLocal() as session:
            await ingest_and_extract(session, tmp_dir, preassigned_ids=preassigned_ids)
    except Exception:  # noqa: BLE001 - background task; surface via logs, not a response
        logger.exception("ingestion background task failed for %s", tmp_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.post("/ingest", status_code=202)
async def ingest(files: list[UploadFile], background_tasks: BackgroundTasks) -> dict:
    tmp_dir = Path(tempfile.mkdtemp(prefix="loom_ingest_"))
    preassigned_ids: dict[str, UUID] = {}

    try:
        for file in files:
            # Basename only — never trust a client-supplied path (traversal guard).
            name = Path(file.filename or "").name
            suffix = Path(name).suffix.lower()
            if suffix not in ACCEPTED_SUFFIXES:
                raise HTTPException(
                    status_code=415,
                    detail=f"Unsupported file type: {suffix} ({file.filename})",
                )

            raw_bytes = await file.read()
            content_hash = hashlib.sha256(raw_bytes).hexdigest()
            # Preserve the original filename so the Document title is meaningful;
            # disambiguate collisions within one request (the pipeline reads the
            # temp dir non-recursively, so every staged file must be uniquely named).
            dest = _unique_dest(tmp_dir, name)
            dest.write_bytes(raw_bytes)
            preassigned_ids.setdefault(content_hash, uuid4())
    except HTTPException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    background_tasks.add_task(_run_ingestion, tmp_dir, preassigned_ids)

    return {
        "doc_ids": [str(doc_id) for doc_id in preassigned_ids.values()],
        "status": "processing",
    }
