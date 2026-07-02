import json
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from google.genai import types as genai_types

from app.extraction.extractor import EntityExtractor, ExtractionError
from app.extraction.schemas import ExtractionResult

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "extraction_fixture.json"


class FakeChunk:
    def __init__(self, text: str):
        self.id = uuid4()
        self.text = text


def _response_with_parsed(result: ExtractionResult | None) -> genai_types.GenerateContentResponse:
    return genai_types.GenerateContentResponse(parsed=result)


def _extractor_for(response: genai_types.GenerateContentResponse) -> EntityExtractor:
    client = MagicMock()
    client.models.generate_content.return_value = response
    return EntityExtractor(client=client)


@pytest.fixture
def fixture_data() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def test_extract_matches_fixture(fixture_data):
    chunk = FakeChunk(fixture_data["chunk_text"])
    expected = ExtractionResult.model_validate(fixture_data["expected_result"])
    extractor = _extractor_for(_response_with_parsed(expected))

    result = extractor.extract(chunk)

    def normalize_entities(entities):
        return {(e.name.strip().lower(), e.type) for e in entities}

    def normalize_relationships(rels):
        return {(r.source.strip().lower(), r.target.strip().lower(), r.relation) for r in rels}

    assert normalize_entities(result.entities) == normalize_entities(expected.entities)
    assert normalize_relationships(result.relationships) == normalize_relationships(expected.relationships)


def test_extract_raises_when_no_parsed_result():
    extractor = _extractor_for(_response_with_parsed(None))

    with pytest.raises(ExtractionError):
        extractor.extract(FakeChunk("some text"))


def test_extraction_error_carries_chunk_id_and_raw_response():
    response = _response_with_parsed(None)
    extractor = _extractor_for(response)
    chunk = FakeChunk("some text")

    with pytest.raises(ExtractionError) as exc_info:
        extractor.extract(chunk)

    assert exc_info.value.chunk_id == chunk.id
    assert exc_info.value.raw_response is response
