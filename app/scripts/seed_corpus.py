"""Seed the Loom knowledge graph with the fictional tech-ecosystem corpus.

Usage (from the repo root):

    cd app
    uv run python -m app.scripts.seed_corpus

Or add a ``make seed`` target that calls this. Requires:
- Postgres running (make db-up && make migrate)
- GEMINI_API_KEY set (used by extract_batch for entity/relationship extraction)

The pipeline is idempotent: re-running is safe because IngestionPipeline deduplicates
on content_hash and the graph upserts are idempotent ON CONFLICT operations.

Because the corpus is ~40 documents the extraction step will exercise the batch API
path (threshold > 10 chunks), which may take several minutes. Progress is printed to
stdout and extraction failures are reported at the end.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap logging before any app imports so all INFO messages are visible.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

from app.extraction.db.session import SessionLocal  # noqa: E402
from app.ingestion.ingest_and_extract import ingest_and_extract  # noqa: E402

CORPUS_DIR = Path(__file__).parent.parent / "data" / "corpus"


async def main() -> None:
    if not CORPUS_DIR.is_dir():
        logger.error("Corpus directory not found: %s", CORPUS_DIR)
        sys.exit(1)

    md_files = sorted(CORPUS_DIR.glob("*.md"))
    if not md_files:
        logger.error("No .md files found in %s", CORPUS_DIR)
        sys.exit(1)

    logger.info("Seeding corpus from %s (%d documents)", CORPUS_DIR, len(md_files))

    with SessionLocal() as session:
        result = await ingest_and_extract(session, CORPUS_DIR)

    logger.info(
        "Seed complete. documents=%d  chunks=%d  extraction_successes=%d  "
        "extraction_failures=%d",
        len(result.documents),
        result.chunk_count,
        result.extraction_successes,
        result.extraction_failures,
    )

    if result.extraction_failures:
        logger.warning(
            "%d chunk(s) failed extraction. Check logs above for details.",
            result.extraction_failures,
        )
    else:
        logger.info("All chunks extracted successfully.")


if __name__ == "__main__":
    asyncio.run(main())
