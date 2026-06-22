import hashlib
import os
from pathlib import Path
from typing import Annotated, Literal, Union

import pdfplumber
from pydantic import BaseModel, Field


class PdfMetadata(BaseModel):
    file_type: Literal["pdf"] = "pdf"
    page_count: int


class TxtMetadata(BaseModel):
    file_type: Literal["txt"] = "txt"


class MdMetadata(BaseModel):
    file_type: Literal["md"] = "md"


DocumentMetadata = Annotated[
    Union[PdfMetadata, TxtMetadata, MdMetadata],
    Field(discriminator="file_type"),
]


class RawDocument(BaseModel):
    source_path: Path
    text: str
    content_hash: str          # sha256 of raw file bytes — used for idempotent re-ingestion
    title: str | None = None   # filename stem by default; loaders may override
    source_metadata: DocumentMetadata


class UnsupportedFileTypeError(Exception):
    def __init__(self, path: Path, suffix: str):
        self.path = path
        self.suffix = suffix
        super().__init__(f"Unsupported file type {suffix!r}: {path}")


def load_pdf(path: Path) -> tuple[str, DocumentMetadata]:
    with pdfplumber.open(path) as pdf:
        pages = [page.extract_text(layout=True) or "" for page in pdf.pages]
    return "\n\n".join(pages), PdfMetadata(page_count=len(pages))


def load_txt(raw_bytes: bytes) -> tuple[str, DocumentMetadata]:
    return raw_bytes.decode("utf-8", errors="replace"), TxtMetadata()


def load_md(raw_bytes: bytes) -> tuple[str, DocumentMetadata]:
    return raw_bytes.decode("utf-8", errors="replace"), MdMetadata()


def load_one(path: Path) -> RawDocument:
    suffix = path.suffix.lower()
    raw_bytes = path.read_bytes()
    content_hash = hashlib.sha256(raw_bytes).hexdigest()

    if suffix == ".pdf":
        text, metadata = load_pdf(path)
    elif suffix == ".txt":
        text, metadata = load_txt(raw_bytes)
    elif suffix == ".md":
        text, metadata = load_md(raw_bytes)
    else:
        raise UnsupportedFileTypeError(path, suffix)

    return RawDocument(
        source_path=path,
        text=text,
        content_hash=content_hash,
        title=path.stem,
        source_metadata=metadata,
    )


def load_documents(directory: Path) -> list[RawDocument]:
    documents = []
    for root, dirnames, filenames in os.walk(directory):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for filename in sorted(filenames):
            if filename.startswith("."):
                continue
            documents.append(load_one(Path(root) / filename))
    return documents
