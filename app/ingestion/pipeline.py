import hashlib
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Chunk as ChunkRow, Document as DocumentRow
from app.ingestion.chunker import chunk_document
from app.ingestion.embedder import embed
from app.ingestion.loaders import RawDocument, load_one


class IngestionPipeline:
    def __init__(self, session: Session):
        self.session = session
        self.settings = get_settings()

    def run(self, source_dir: Path) -> list[DocumentRow]:
        ingested: list[DocumentRow] = []

        for path in sorted(source_dir.iterdir()):
            raw_bytes = path.read_bytes()
            content_hash = hashlib.sha256(raw_bytes).hexdigest()

            existing = self.session.execute(
                select(DocumentRow).where(DocumentRow.content_hash == content_hash)
            ).scalar_one_or_none()
            if existing:
                continue

            raw_doc: RawDocument = load_one(path)
            if raw_doc is None:
                continue

            chunks = chunk_document(raw_doc, self.settings.chunk_size, self.settings.chunk_overlap)
            embeddings = embed([chunk.text for chunk in chunks])

            doc = DocumentRow(
                id=uuid4(),
                source_path=str(path),
                content_hash=content_hash,
                title=raw_doc.title,
                source_metadata=raw_doc.source_metadata.model_dump(),
            )
            self.session.add(doc)

            self.session.add_all([
                ChunkRow(
                    id=uuid4(),
                    document_id=doc.id,
                    ordinal=chunk.ordinal,
                    text=chunk.text,
                    token_count=chunk.token_count,
                    embedding=embeddings[i].tolist(),
                )
                for i, chunk in enumerate(chunks)
            ])

            self.session.commit()
            ingested.append(doc)

        return ingested
