"""Tests for POST /ingest.

Extraction (`extract_batch` / `store_extraction_results`) and the ML models
(`chunk_document` / `embed`) are stubbed so the test runs without Gemini or
torch. Ingestion persistence runs for real against Postgres. TestClient executes
BackgroundTasks synchronously after the response, so the DB assertion holds
in-process.
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.extraction.batch import BatchResult
from app.extraction.db.models import Document as DocumentRow
from app.ingestion.chunker import ChunkResult
from app.main import app


def _fake_chunk(doc, chunk_size, chunk_overlap):
    return [
        ChunkResult(
            source_path=doc.source_path,
            ordinal=0,
            text=doc.text[:200],
            token_count=min(len(doc.text.split()), chunk_size) or 1,
            start_token_idx=0,
            end_token_idx=min(len(doc.text.split()), chunk_size) or 1,
        )
    ]


def _fake_embed(texts):
    return np.zeros((len(texts), 768), dtype=np.float32)


async def _fake_extract_batch(chunks, *args, **kwargs):
    return BatchResult()


@pytest.fixture(autouse=True)
def mock_pipeline(monkeypatch):
    monkeypatch.setattr("app.ingestion.pipeline.chunk_document", _fake_chunk)
    monkeypatch.setattr("app.ingestion.pipeline.embed", _fake_embed)
    monkeypatch.setattr("app.ingestion.ingest_and_extract.extract_batch", _fake_extract_batch)
    monkeypatch.setattr(
        "app.ingestion.ingest_and_extract.store_extraction_results",
        lambda session, results: None,
    )


def test_valid_txt_returns_202_and_persists_document(db_session):
    client = TestClient(app)

    response = client.post(
        "/ingest",
        files=[("files", ("hello.txt", b"Hello, this is a test document.", "text/plain"))],
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "processing"
    assert len(body["doc_ids"]) == 1

    # BackgroundTasks ran; the doc id returned should now be in the DB.
    doc_id = body["doc_ids"][0]
    doc = db_session.execute(
        select(DocumentRow).where(DocumentRow.id == doc_id)
    ).scalar_one()
    assert doc.title == "hello"
    assert len(doc.chunks) == 1


def test_docx_in_batch_returns_415_naming_the_file(db_session):
    client = TestClient(app)

    response = client.post(
        "/ingest",
        files=[
            ("files", ("good.txt", b"fine content", "text/plain")),
            ("files", ("report.docx", b"bad content", "application/octet-stream")),
        ],
    )

    assert response.status_code == 415
    detail = response.json()["detail"]
    assert "report.docx" in detail
    assert ".docx" in detail

    # Nothing should have been ingested when validation rejects the batch.
    docs = db_session.execute(select(DocumentRow)).scalars().all()
    assert docs == []
