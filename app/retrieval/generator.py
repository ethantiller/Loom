"""Grounded, citation-enforced answer generation.

Takes a :class:`RetrievalContext` and produces an :class:`AnswerResult` whose
answer is constrained to the supplied chunk text and graph facts. Citation
tokens are parsed out of the model output with a regex and each cited id is
validated against the ids actually present in the context, so a hallucinated
``[chunk:...]`` / ``[entity:...]`` id is detectable rather than silently trusted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from google import genai
from google.genai import types as genai_types

from app.config import get_settings
from app.retrieval.hybrid import RetrievalContext
from app.retrieval.prompts import ANSWER_SYSTEM_PROMPT

ANSWER_MODEL = "gemini-2.5-flash"

# Matches [chunk:<id>] and [entity:<id>] citation tokens. The id charset covers
# UUIDs (hex + hyphens) which is what chunk/entity ids are.
_CITATION_RE = re.compile(r"\[(chunk|entity):([0-9a-fA-F-]+)\]")


@dataclass(frozen=True)
class Citation:
    kind: str  # "chunk" or "entity"
    id: str


@dataclass
class AnswerResult:
    answer: str
    citations: list[Citation] = field(default_factory=list)  # valid, deduped, in order
    invalid_citations: list[str] = field(default_factory=list)  # cited ids not in context
    raw: str = ""


def _build_client(client: genai.Client | None) -> genai.Client:
    if client is not None:
        return client
    api_key = get_settings().gemini_api_key
    if not api_key:
        raise ValueError("GEMINI_API_KEY is required to generate answers")
    return genai.Client(api_key=api_key)


def format_context(context: RetrievalContext) -> str:
    """Render a RetrievalContext into the tagged block the model reads/cites."""
    parts: list[str] = []
    for chunk in context.chunks:
        parts.append(f"[chunk:{chunk.id}]\n{chunk.text}")
    if context.entities:
        legend = "\n".join(f"[entity:{eid}] {name}" for eid, name in context.entities.items())
        parts.append("Entities:\n" + legend)
    if context.graph_facts:
        parts.append("Graph facts:\n" + context.graph_facts)
    return "\n\n".join(parts)


def validate_citations(
    text: str, context: RetrievalContext
) -> tuple[list[Citation], list[str]]:
    """Parse citation tokens from ``text`` and split them by presence in context.

    Returns ``(valid_citations, invalid_ids)``. Valid citations are deduped with
    first-seen order preserved; invalid ids are those cited but not present in
    the context object (hallucinations).
    """
    chunk_ids = {str(c.id) for c in context.chunks}
    entity_ids = set(context.entities)

    valid: list[Citation] = []
    seen: set[tuple[str, str]] = set()
    invalid: list[str] = []
    for kind, cid in _CITATION_RE.findall(text):
        known = cid in chunk_ids if kind == "chunk" else cid in entity_ids
        if not known:
            if cid not in invalid:
                invalid.append(cid)
            continue
        key = (kind, cid)
        if key in seen:
            continue
        seen.add(key)
        valid.append(Citation(kind=kind, id=cid))
    return valid, invalid


def generate_answer(
    question: str,
    context: RetrievalContext,
    *,
    client: genai.Client | None = None,
    model: str = ANSWER_MODEL,
) -> AnswerResult:
    llm = _build_client(client)
    prompt = f"QUESTION:\n{question}\n\nCONTEXT:\n{format_context(context)}"

    response = llm.models.generate_content(
        model=model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(system_instruction=ANSWER_SYSTEM_PROMPT),
    )
    raw = response.text or ""

    citations, invalid = validate_citations(raw, context)
    return AnswerResult(answer=raw, citations=citations, invalid_citations=invalid, raw=raw)
