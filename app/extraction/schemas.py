from typing import Literal

from google.genai import types as genai_types
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


def build_extraction_tool() -> genai_types.Tool:
    function = genai_types.FunctionDeclaration(
        name="record_extraction",
        description="Record the entities and relationships found in the chunk text.",
        parameters_json_schema=ExtractionResult.model_json_schema(),
    )
    return genai_types.Tool(function_declarations=[function])
