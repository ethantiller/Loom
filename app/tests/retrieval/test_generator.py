"""Tests for retrieval.generator — grounded answers and citation validation.

The genai client is mocked (per tests/extraction/test_extractor.py), so no API
key or network is needed. Chunks are lightweight stand-ins exposing ``id`` and
``text``, which is all the generator reads.
"""

from unittest.mock import MagicMock
from uuid import uuid4

from app.retrieval.generator import Citation, generate_answer, validate_citations
from app.retrieval.hybrid import RetrievalContext
from app.retrieval.prompts import NO_INFO_SENTENCE


class FakeChunk:
    def __init__(self, text: str):
        self.id = uuid4()
        self.text = text


def _generator_for(answer_text: str):
    response = MagicMock()
    response.text = answer_text
    client = MagicMock()
    client.models.generate_content.return_value = response
    return client


def _context(chunks=None, entities=None, graph_facts=""):
    return RetrievalContext(
        chunks=chunks or [],
        graph_facts=graph_facts,
        total_tokens=0,
        entities=entities or {},
    )


def test_valid_citations_all_resolve():
    chunk = FakeChunk("Ada Lovelace wrote the first algorithm.")
    entity_id = str(uuid4())
    ctx = _context(chunks=[chunk], entities={entity_id: "Ada Lovelace"},
                   graph_facts="Ada Lovelace → wrote → algorithm")
    answer = f"Ada wrote the first algorithm [chunk:{chunk.id}] [entity:{entity_id}]."
    client = _generator_for(answer)

    result = generate_answer("What did Ada do?", ctx, client=client)

    assert result.invalid_citations == []
    assert Citation("chunk", str(chunk.id)) in result.citations
    assert Citation("entity", entity_id) in result.citations


def test_hallucinated_citation_is_flagged():
    chunk = FakeChunk("Some grounded fact.")
    ctx = _context(chunks=[chunk])
    fake_id = str(uuid4())  # never present in the context
    answer = f"Grounded [chunk:{chunk.id}] but also made up [chunk:{fake_id}]."
    client = _generator_for(answer)

    result = generate_answer("q", ctx, client=client)

    assert fake_id in result.invalid_citations
    assert Citation("chunk", str(chunk.id)) in result.citations
    assert Citation("chunk", fake_id) not in result.citations


def test_no_info_response_when_context_empty():
    ctx = _context()  # nothing relevant
    client = _generator_for(NO_INFO_SENTENCE)

    result = generate_answer("Unanswerable question?", ctx, client=client)

    assert NO_INFO_SENTENCE in result.answer
    assert result.citations == []
    assert result.invalid_citations == []


def test_validate_citations_dedupes_valid_and_invalid():
    chunk = FakeChunk("x")
    ctx = _context(chunks=[chunk])
    fake_id = str(uuid4())
    text = (
        f"[chunk:{chunk.id}] repeated [chunk:{chunk.id}] "
        f"and [chunk:{fake_id}] repeated [chunk:{fake_id}]"
    )

    valid, invalid = validate_citations(text, ctx)

    assert valid == [Citation("chunk", str(chunk.id))]  # deduped
    assert invalid == [fake_id]  # deduped
