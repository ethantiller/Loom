"""Hybrid (vector + graph) retriever.

Composes the independently-tested retrieval building blocks into a single
end-to-end query flow:

    embed_query -> similarity_search -> find_seed_entities -> expand_subgraph
                -> subgraph_to_context

and packages the result as a token-budgeted :class:`RetrievalContext`. Graph
facts are treated as *supplementary*: when the combined context exceeds
``settings.max_context_tokens`` they are trimmed first, and only if the chunk
text alone still overflows do we drop whole (least-relevant) chunks rather than
truncating text mid-sentence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.config import get_settings
from app.extraction.db.models import Chunk
from app.ingestion.chunker import count_tokens
from app.ingestion.embedder import embed_query
from app.retrieval.graph_builder import build_graph_from_db
from app.retrieval.graph_traversal import (
    expand_subgraph,
    find_seed_entities,
    subgraph_to_context,
)
from app.retrieval.vector_search import similarity_search


@dataclass
class RetrievalContext:
    """A token-budgeted bundle of retrieved context for answer generation.

    ``chunks`` holds SQLAlchemy ORM rows in descending relevance order.
    ``entities`` maps ``entity_id (str) -> name`` for every entity in the
    expanded subgraph; the answer generator uses it to expose real entity IDs
    for citation and to reject hallucinated ``[entity:{id}]`` citations.
    """

    chunks: list[Chunk]
    graph_facts: str
    total_tokens: int
    entities: dict[str, str] = field(default_factory=dict)


class HybridRetriever:
    def __init__(self, session: Session):
        self.session = session

    def retrieve(self, query: str, k: int = 5, n_hops: int = 2) -> RetrievalContext:
        budget = get_settings().max_context_tokens

        query_embedding = embed_query(query)
        chunks = similarity_search(self.session, query_embedding, k)

        graph = build_graph_from_db(self.session)
        seeds: set = set()
        for chunk in chunks:
            seeds.update(find_seed_entities(chunk.id, self.session))
        subgraph = expand_subgraph(graph, list(seeds), n_hops=n_hops)
        entities = {str(nid): name for nid, name in subgraph.nodes(data="name")}

        chunk_tokens = sum(c.token_count for c in chunks)

        if chunk_tokens > budget:
            # Chunk text alone overflows: drop whole chunks from the tail (least
            # relevant first) until it fits. No room remains for graph facts.
            while chunks and chunk_tokens > budget:
                chunk_tokens -= chunks.pop().token_count
            graph_facts = ""
        else:
            # Graph facts absorb the remaining budget (supplementary → trimmed first).
            graph_facts = subgraph_to_context(subgraph, token_budget=budget - chunk_tokens)

        total_tokens = chunk_tokens + count_tokens(graph_facts)

        return RetrievalContext(
            chunks=chunks,
            graph_facts=graph_facts,
            total_tokens=total_tokens,
            entities=entities,
        )
