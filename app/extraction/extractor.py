from __future__ import annotations

from typing import Any

from google import genai
from google.genai import types as genai_types

from app.config import get_settings
from app.extraction.db.models import Chunk
from app.extraction.prompts import EXTRACTION_SYSTEM_PROMPT
from app.extraction.schemas import ExtractionResult

EXTRACTION_MODEL = "gemini-2.5-flash"


class ExtractionError(Exception):
    def __init__(self, chunk_id: Any, raw_response: Any):
        self.chunk_id = chunk_id
        self.raw_response = raw_response
        super().__init__(f"entity extraction failed for chunk {chunk_id!r}")


class EntityExtractor:
    def __init__(self, client: genai.Client | None = None, model: str = EXTRACTION_MODEL):
        self._client = client or genai.Client(api_key=get_settings().gemini_api_key)
        self._model = model

    def extract(self, chunk: Chunk) -> ExtractionResult:
        response = self._client.models.generate_content(
            model=self._model,
            contents=chunk.text,
            config=genai_types.GenerateContentConfig(
                system_instruction=EXTRACTION_SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=ExtractionResult,
            ),
        )

        result = response.parsed
        if not isinstance(result, ExtractionResult):
            raise ExtractionError(chunk.id, response)
        return result
