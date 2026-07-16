"""Graph traversal utilities for graph-augmented retrieval.

Given the entities mentioned in a retrieved chunk (the *seeds*), expand outward
to a neighbourhood subgraph and render it as text triples for the LLM context.
"""

from uuid import UUID

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.extraction.db.models import EntityMention
from app.ingestion.chunker import count_tokens


def find_seed_entities(chunk_id: UUID, session: Session) -> list[UUID]:
    """Return the IDs of every entity mentioned in the given chunk."""
    rows = session.execute(
        select(EntityMention.entity_id).where(EntityMention.chunk_id == chunk_id)
    ).scalars().all()
    return list(rows)


def expand_subgraph(
    graph: nx.MultiDiGraph, seeds: list[UUID], n_hops: int = 2
) -> nx.MultiDiGraph:
    """Return the union of the ``n_hops`` neighbourhoods around each seed.

    Traversal is deliberately **undirected**: relationships are stored with a
    direction (source -> target), but for retrieval we want everything an entity
    is "connected to" regardless of which way the edge points, so we compute the
    ego graph over an undirected view. The returned subgraph is induced back on
    the original directed ``MultiDiGraph``, preserving edge direction and
    per-relation-type keys for rendering.
    """
    nodes: set[UUID] = set()
    undirected = graph.to_undirected(as_view=True)
    for seed in seeds:
        if seed not in graph:
            continue
        nodes.update(nx.ego_graph(undirected, seed, radius=n_hops).nodes)
    return graph.subgraph(nodes).copy()


def subgraph_to_context(
    subgraph: nx.MultiDiGraph, token_budget: int | None = None
) -> str:
    """Render a subgraph as newline-separated ``src -> relation -> tgt`` triples.

    Identical triples are de-duplicated (first-seen order preserved). Lines are
    accumulated until adding the next one would exceed ``token_budget`` tokens
    (measured with the embedding model's tokenizer), then truncated. Defaults to
    ``settings.max_context_tokens``.
    """
    if token_budget is None:
        token_budget = get_settings().max_context_tokens

    seen: set[str] = set()
    lines: list[str] = []
    for src, tgt, data in subgraph.edges(data=True):
        src_name = subgraph.nodes[src].get("name", str(src))
        tgt_name = subgraph.nodes[tgt].get("name", str(tgt))
        line = f"{src_name} → {data['relation']} → {tgt_name}"
        if line in seen:
            continue
        seen.add(line)

        candidate = "\n".join(lines + [line])
        if count_tokens(candidate) > token_budget:
            break
        lines.append(line)

    return "\n".join(lines)
