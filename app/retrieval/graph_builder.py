"""Build an in-memory NetworkX graph from the stored entities and relationships.

The graph is rebuilt on demand per query rather than cached; at the current
scale (a few hundred nodes) this is well under a second. Revisit caching only if
profiling later shows it to be a bottleneck.
"""

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extraction.db.models import Entity, Relationship


def build_graph_from_db(session: Session) -> nx.MultiDiGraph:
    """Load all entities and relationships into a directed multigraph.

    A ``MultiDiGraph`` keyed by ``relation_type`` is used so that two distinct
    relation types between the same pair of entities are kept as separate edges
    instead of overwriting one another.
    """
    graph = nx.MultiDiGraph()

    for entity in session.execute(select(Entity)).scalars():
        graph.add_node(entity.id, name=entity.name, type=entity.entity_type)

    for rel in session.execute(select(Relationship)).scalars():
        graph.add_edge(
            rel.source_entity_id,
            rel.target_entity_id,
            key=rel.relation_type,
            relation=rel.relation_type,
            chunk_id=rel.source_chunk_id,
        )

    return graph
