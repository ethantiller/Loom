"""End-to-end tests for IngestionPipeline.

Both `embed` and `chunk_document` are mocked so the tests run without
downloading any ML models. The DB layer uses a real Postgres connection
(same DATABASE_URL as the app) to exercise the full persistence path.
"""

import numpy as np
import pytest
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import select

from app.db.models import Chunk as ChunkRow, Document as DocumentRow
from app.ingestion.chunker import ChunkResult
from app.ingestion.pipeline import IngestionPipeline


def _fake_chunk(doc, chunk_size, chunk_overlap):
    return [
        ChunkResult(
            source_path=doc.source_path,
            ordinal=0,
            text=doc.text[:200],
            token_count=min(len(doc.text.split()), chunk_size),
            start_token_idx=0,
            end_token_idx=min(len(doc.text.split()), chunk_size),
        )
    ]


def _fake_embed(texts):
    return np.zeros((len(texts), 768), dtype=np.float32)


@pytest.fixture(autouse=True)
def mock_ml(monkeypatch):
    monkeypatch.setattr("app.ingestion.pipeline.chunk_document", _fake_chunk)
    monkeypatch.setattr("app.ingestion.pipeline.embed", _fake_embed)


def test_txt_file_creates_document_and_chunk(tmp_path, db_session):
    (tmp_path / "hello.txt").write_text("Hello, this is a test document.")

    result = IngestionPipeline(db_session).run(tmp_path)

    assert len(result) == 1
    doc = result[0]
    assert doc.title == "hello"

    db_doc = db_session.execute(
        select(DocumentRow).where(DocumentRow.id == doc.id)
    ).scalar_one()
    assert db_doc.source_metadata["file_type"] == "txt"

    chunks = db_session.execute(
        select(ChunkRow).where(ChunkRow.document_id == doc.id)
    ).scalars().all()
    assert len(chunks) == 1
    assert chunks[0].ordinal == 0
    assert chunks[0].embedding is not None


def test_md_file_creates_document_and_chunk(tmp_path, db_session):
    (tmp_path / "notes.md").write_text("# Title\n\nSome markdown content.")

    result = IngestionPipeline(db_session).run(tmp_path)

    assert len(result) == 1
    assert result[0].title == "notes"

    db_doc = db_session.execute(
        select(DocumentRow).where(DocumentRow.id == result[0].id)
    ).scalar_one()
    assert db_doc.source_metadata["file_type"] == "md"


def test_idempotent_second_run_skips_existing(tmp_path, db_session):
    (tmp_path / "doc.txt").write_text("Some content.")

    pipeline = IngestionPipeline(db_session)
    first = pipeline.run(tmp_path)
    second = pipeline.run(tmp_path)

    assert len(first) == 1
    assert len(second) == 0

    all_docs = db_session.execute(select(DocumentRow)).scalars().all()
    assert len(all_docs) == 1


def test_multiple_files_all_ingested(tmp_path, db_session):
    (tmp_path / "a.txt").write_text("File A content.")
    (tmp_path / "b.txt").write_text("File B content.")
    (tmp_path / "c.md").write_text("File C content.")

    result = IngestionPipeline(db_session).run(tmp_path)

    assert len(result) == 3
    assert {doc.title for doc in result} == {"a", "b", "c"}

    all_chunks = db_session.execute(select(ChunkRow)).scalars().all()
    assert len(all_chunks) == 3


def test_pdf_file_ingested(db_session):
    data_dir = Path(__file__).parent.parent / "data"

    result = IngestionPipeline(db_session).run(data_dir)

    assert len(result) == 1
    db_doc = db_session.execute(
        select(DocumentRow).where(DocumentRow.id == result[0].id)
    ).scalar_one()
    assert db_doc.source_metadata["file_type"] == "pdf"
    assert db_doc.source_metadata["page_count"] >= 1
