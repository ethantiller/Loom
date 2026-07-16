"""Agentic retrieval controller (bounded ReAct loop).

Drives a Gemini model through a tool-use loop, exposing three tools:
``vector_search``, ``expand_graph`` and ``finalize_answer``. The controller
executes the requested Python function, feeds the result back, and repeats until
the model finalizes or the step budget (``settings.retrieval_max_steps``) is
exhausted. On exhaustion it forces one final grounded generation from whatever
context was accumulated and marks the result ``truncated``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from google.genai import types as genai_types
from sqlalchemy.orm import Session

from app.config import get_settings
from app.extraction.db.models import Chunk
from app.ingestion.chunker import count_tokens
from app.ingestion.embedder import embed_query
from app.retrieval.generator import (
    Citation,
    _build_client,
    generate_answer,
    validate_citations,
)
from app.retrieval.graph_builder import build_graph_from_db
from app.retrieval.graph_traversal import expand_subgraph, subgraph_to_context
from app.retrieval.hybrid import RetrievalContext
from app.retrieval.prompts import RETRIEVAL_SYSTEM_PROMPT
from app.retrieval.vector_search import similarity_search

AGENT_MODEL = "gemini-2.5-flash"


@dataclass
class AgentResult:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    context: RetrievalContext = field(default_factory=lambda: RetrievalContext([], "", 0))
    steps: list[dict] = field(default_factory=list)
    truncated: bool = False


def _tool_config() -> genai_types.GenerateContentConfig:
    string = genai_types.Schema(type=genai_types.Type.STRING)
    integer = genai_types.Schema(type=genai_types.Type.INTEGER)
    tools = genai_types.Tool(function_declarations=[
        genai_types.FunctionDeclaration(
            name="vector_search",
            description="Semantic search over document chunks. Returns the most relevant chunk text.",
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={"query": string, "k": integer},
                required=["query"],
            ),
        ),
        genai_types.FunctionDeclaration(
            name="expand_graph",
            description="Expand the knowledge graph around named entities to surface relationships.",
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "seed_entity_names": genai_types.Schema(
                        type=genai_types.Type.ARRAY, items=string
                    ),
                    "n_hops": integer,
                },
                required=["seed_entity_names"],
            ),
        ),
        genai_types.FunctionDeclaration(
            name="finalize_answer",
            description="Submit the final answer with inline [chunk:<id>]/[entity:<id>] citations.",
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "answer": string,
                    "citations": genai_types.Schema(type=genai_types.Type.ARRAY, items=string),
                },
                required=["answer"],
            ),
        ),
    ])
    return genai_types.GenerateContentConfig(
        system_instruction=RETRIEVAL_SYSTEM_PROMPT,
        tools=[tools],
        automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
    )


class RetrievalAgent:
    def __init__(self, session: Session, client=None, model: str = AGENT_MODEL):
        self.session = session
        self.model = model
        self._client = _build_client(client)
        # Context accumulated across tool calls.
        self._chunks: dict = {}          # chunk_id -> Chunk
        self._entities: dict[str, str] = {}
        self._graph_facts: list[str] = []

    # ---- tools -------------------------------------------------------------

    def _vector_search(self, query: str, k: int = 5) -> str:
        chunks = similarity_search(self.session, embed_query(query), k)
        for chunk in chunks:
            self._chunks[chunk.id] = chunk
        if not chunks:
            return "No chunks found."
        return "\n\n".join(f"[chunk:{c.id}] {c.text}" for c in chunks)

    def _expand_graph(self, seed_entity_names: list[str], n_hops: int = 2) -> str:
        graph = build_graph_from_db(self.session)
        wanted = {n.strip().lower() for n in seed_entity_names}
        seeds = [nid for nid, name in graph.nodes(data="name")
                 if (name or "").strip().lower() in wanted]
        subgraph = expand_subgraph(graph, seeds, n_hops=n_hops)
        for nid, name in subgraph.nodes(data="name"):
            self._entities[str(nid)] = name
        facts = subgraph_to_context(subgraph)
        if facts:
            self._graph_facts.append(facts)
        return facts or "No graph facts found."

    def _dispatch(self, name: str, args: dict) -> str:
        if name == "vector_search":
            return self._vector_search(args["query"], args.get("k") or 5)
        if name == "expand_graph":
            return self._expand_graph(args["seed_entity_names"], args.get("n_hops") or 2)
        return f"Unknown tool: {name}"

    # ---- accumulated context ----------------------------------------------

    def _build_context(self) -> RetrievalContext:
        chunks: list[Chunk] = list(self._chunks.values())
        # De-duplicate accumulated fact blocks, first-seen order preserved.
        seen: set[str] = set()
        lines: list[str] = []
        for block in self._graph_facts:
            for line in block.split("\n"):
                if line and line not in seen:
                    seen.add(line)
                    lines.append(line)
        graph_facts = "\n".join(lines)
        total = sum(c.token_count for c in chunks) + count_tokens(graph_facts)
        return RetrievalContext(
            chunks=chunks, graph_facts=graph_facts, total_tokens=total,
            entities=dict(self._entities),
        )

    def _finalize(self, answer: str, steps: list[dict], truncated: bool) -> AgentResult:
        context = self._build_context()
        citations, _ = validate_citations(answer, context)
        return AgentResult(
            answer=answer, citations=citations, context=context,
            steps=steps, truncated=truncated,
        )

    # ---- main loop ---------------------------------------------------------

    def run(self, question: str) -> AgentResult:
        max_steps = get_settings().retrieval_max_steps
        config = _tool_config()
        contents: list = [
            genai_types.Content(role="user", parts=[genai_types.Part(text=question)])
        ]
        steps: list[dict] = []

        step_count = 0
        while step_count < max_steps:
            step_count += 1
            response = self._client.models.generate_content(
                model=self.model, contents=contents, config=config
            )
            calls = response.function_calls
            if not calls:
                # Model answered directly without a tool call.
                return self._finalize(response.text or "", steps, truncated=False)

            contents.append(response.candidates[0].content)
            for call in calls:
                steps.append({"name": call.name, "args": dict(call.args)})
                if call.name == "finalize_answer":
                    return self._finalize(call.args.get("answer", ""), steps, truncated=False)
                output = self._dispatch(call.name, call.args)
                contents.append(genai_types.Content(
                    role="user",
                    parts=[genai_types.Part.from_function_response(
                        name=call.name, response={"result": output}
                    )],
                ))

        # Step budget exhausted without finalizing: force one grounded generation.
        context = self._build_context()
        result = generate_answer(question, context, client=self._client, model=self.model)
        return AgentResult(
            answer=result.answer, citations=result.citations, context=context,
            steps=steps, truncated=True,
        )
