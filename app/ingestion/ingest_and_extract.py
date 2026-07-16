"""End-to-end ingestion: documents/chunks + knowledge-graph extraction.

``IngestionPipeline.run`` only persists Documents and Chunks; the entity/
relationship graph is a separate extraction stage. This helper chains the two so
callers get a fully populated store (documents → chunks → entities → relationships)
from a single call. It is shared by the ``/ingest`` endpoint's background task and
the corpus seed script so the two stay in lockstep.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.extraction.batch import extract_batch
from app.extraction.db.models import Document as DocumentRow
from app.extraction.graph_store import store_extraction_results
from app.ingestion.pipeline import IngestionPipeline

logger = logging.getLogger(__name__)


@dataclass
class IngestAndExtractResult:
    documents: list[DocumentRow]
    chunk_count: int
    extraction_successes: int
    extraction_failures: int


async def ingest_and_extract(
    session: Session,
    source_dir: Path,
    preassigned_ids: dict[str, UUID] | None = None,
) -> IngestAndExtractResult:
    """Ingest ``source_dir`` then extract and persist its knowledge graph.

    Runs ``IngestionPipeline.run`` (blocking) to create Documents + Chunks, then
    ``extract_batch`` over every new chunk and ``store_extraction_results`` to
    persist entities/relationships. Per-chunk extraction failures are logged, not
    raised, so one bad chunk never aborts the whole batch.
    """
    documents = IngestionPipeline(session).run(source_dir, preassigned_ids=preassigned_ids)
    chunks = [chunk for doc in documents for chunk in doc.chunks]

    result = await extract_batch(chunks)
    store_extraction_results(session, result.successes)

    if result.failures:
        logger.warning(
            "extraction completed with %d failure(s) out of %d chunk(s)",
            len(result.failures),
            len(chunks),
        )

    return IngestAndExtractResult(
        documents=documents,
        chunk_count=len(chunks),
        extraction_successes=len(result.successes),
        extraction_failures=len(result.failures),
    )
