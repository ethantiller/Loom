"""Evaluation scoring helpers for the GraphRAG eval harness.

Two metrics are implemented:

``recall_at_k(qa_entry, context, session)``
    Resolves each ``gold_entity`` name to its database row (via
    ``Entity.normalized_name``), finds the chunk IDs it was mentioned in
    (through ``EntityMention``), and checks whether any of those chunk IDs
    appears in ``context.chunks``. Returns ``True`` if at least one gold
    entity's source chunk was retrieved.

``answer_correctness(question, expected, actual, *, client=None)``
    Primary judge: Gemini LLM-as-judge with a simple correct/incorrect prompt.
    Fallback (when no GEMINI_API_KEY or ``client``): token-overlap ratio — the
    fraction of expected-answer tokens that also appear in the actual answer. A
    ratio ≥ 0.5 is considered correct.
"""

from __future__ import annotations

import logging
import re
from collections import Counter

from sqlalchemy.orm import Session

from app.extraction.db.models import Chunk, Entity, EntityMention
from app.extraction.graph_store import _normalize
from app.retrieval.hybrid import RetrievalContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Recall@k
# ---------------------------------------------------------------------------


def recall_at_k(
    gold_entities: list[str],
    context: RetrievalContext,
    session: Session,
) -> bool:
    """Return True if at least one gold entity's source chunk was retrieved.

    For each name in ``gold_entities``:
    1. Normalize the name and look up the Entity row.
    2. Load all EntityMention rows linking that entity to chunks.
    3. Check whether any of those chunk IDs appears in ``context.chunks``.

    Returns True on the first hit; False only if no gold entity's chunk was
    found anywhere in the retrieved context.
    """
    retrieved_chunk_ids = {str(c.id) for c in context.chunks}

    for name in gold_entities:
        normalized = _normalize(name)
        entity = (
            session.query(Entity)
            .filter(Entity.normalized_name == normalized)
            .first()
        )
        if entity is None:
            logger.debug("Gold entity %r (normalized: %r) not found in DB", name, normalized)
            continue

        mentions = (
            session.query(EntityMention)
            .filter(EntityMention.entity_id == entity.id)
            .all()
        )
        for mention in mentions:
            if str(mention.chunk_id) in retrieved_chunk_ids:
                return True

    return False


# ---------------------------------------------------------------------------
# Answer correctness
# ---------------------------------------------------------------------------

_JUDGE_PROMPT = """\
You are an answer judge. Given a QUESTION, an EXPECTED answer, and an ACTUAL answer,
decide whether the ACTUAL answer is correct.

An answer is correct if it conveys the same key facts as the EXPECTED answer, even if
phrased differently. Minor omissions are acceptable; factual errors are not.

Respond with exactly one word: correct or incorrect.

QUESTION: {question}
EXPECTED: {expected}
ACTUAL: {actual}"""


def _token_overlap(expected: str, actual: str) -> bool:
    """Fallback correctness: fraction of expected tokens in actual >= 0.5."""
    def tokens(text: str) -> Counter:
        return Counter(re.findall(r"\b\w+\b", text.lower()))

    exp_tokens = tokens(expected)
    act_tokens = tokens(actual)
    if not exp_tokens:
        return True  # trivially correct if expected is empty
    overlap = sum(min(exp_tokens[t], act_tokens[t]) for t in exp_tokens)
    ratio = overlap / sum(exp_tokens.values())
    logger.debug("Token overlap ratio: %.2f", ratio)
    return ratio >= 0.5


def answer_correctness(
    question: str,
    expected: str,
    actual: str,
    *,
    client=None,
) -> bool:
    """Judge whether ``actual`` correctly answers ``question`` vs ``expected``.

    Uses Gemini LLM-as-judge when ``client`` is supplied or GEMINI_API_KEY is
    set; falls back to token-overlap when neither is available.
    """
    # Attempt LLM judge.
    llm = None
    if client is not None:
        llm = client
    else:
        try:
            from app.config import get_settings
            from google import genai

            settings = get_settings()
            if settings.gemini_api_key:
                llm = genai.Client(api_key=settings.gemini_api_key)
        except Exception:
            pass

    if llm is not None:
        try:
            prompt = _JUDGE_PROMPT.format(
                question=question, expected=expected, actual=actual
            )
            response = llm.models.generate_content(
                model="gemini-2.5-flash", contents=prompt
            )
            verdict = (response.text or "").strip().lower()
            logger.debug("LLM judge verdict: %r", verdict)
            return "correct" in verdict
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM judge failed, falling back to token overlap: %s", exc)

    return _token_overlap(expected, actual)
