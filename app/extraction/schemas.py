from typing import Literal

from pydantic import BaseModel


class ExtractedEntity(BaseModel):
    name: str
    type: Literal["PERSON", "ORG", "PRODUCT", "CONCEPT", "EVENT"]


class ExtractedRelationship(BaseModel):
    source: str
    target: str
    relation: str  # short verb phrase, e.g. "founded_by"


class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity]
    relationships: list[ExtractedRelationship]
