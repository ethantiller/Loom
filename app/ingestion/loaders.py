from pathlib import Path
from typing import Annotated, Literal, Union

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
