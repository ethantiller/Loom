"""Persist extraction results into the knowledge-graph tables.

Writes are idempotent: re-running extraction over the same chunks must not
duplicate entities, relationships, or mentions. Idempotency is enforced at the
database level via ``ON CONFLICT`` against the unique constraints defined in
:mod:`app.extraction.db.models` (``uq_entities_normalized_name``,
``uq_relationship``, and the ``entity_mentions`` composite primary key), so the
outcome is independent of insertion order or concurrent writers.
"""

import re
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.extraction.db.models import Chunk, Entity, EntityMention, Relationship
from app.extraction.schemas import ExtractionResult


def _normalize(name: str) -> str:
    """Collapse surface variants ("OpenAI", "Open AI") onto one key.

    Lowercase, strip, and drop punctuation, then remove all whitespace. The
    whitespace removal is deliberate: the ticket's goal is that "OpenAI" and
    "Open AI" resolve to the same entity, which is only possible if internal
    spaces are collapsed (the base ``[^\\w\\s]`` substitution preserves them).
    This is the value stored in ``Entity.normalized_name`` and used to resolve
    relationship endpoints.
    """
    without_punct = re.sub(r"[^\w\s]", "", name.lower().strip())
    return re.sub(r"\s+", "", without_punct)


def upsert_entity(session: Session, name: str, entity_type: str) -> Entity:
    """Insert an entity, or return the existing one for the same normalized name.

    On conflict the display ``name`` is refreshed to the latest surface form so
    the most recently seen spelling wins; the row identity is unchanged.
    """
    stmt = (
        pg_insert(Entity)
        .values(name=name, normalized_name=_normalize(name), entity_type=entity_type)
        .on_conflict_do_update(
            index_elements=["normalized_name"],
            set_={"name": pg_insert(Entity).excluded.name},
        )
        .returning(Entity)
    )
    return session.execute(stmt).scalar_one()


def upsert_relationship(
    session: Session,
    source_id: UUID,
    target_id: UUID,
    relation_type: str,
    source_chunk_id: UUID,
) -> None:
    """Insert a (source, target, relation) edge, ignoring duplicates.

    The ``uq_relationship`` constraint means the same triple is stored once; a
    later mention of the same triple from a different chunk is a no-op.
    """
    stmt = (
        pg_insert(Relationship)
        .values(
            source_entity_id=source_id,
            target_entity_id=target_id,
            relation_type=relation_type,
            source_chunk_id=source_chunk_id,
        )
        .on_conflict_do_nothing(
            index_elements=["source_entity_id", "target_entity_id", "relation_type"]
        )
    )
    session.execute(stmt)


def _add_mention(session: Session, entity_id: UUID, chunk_id: UUID) -> None:
    """Record that ``entity_id`` was mentioned in ``chunk_id`` (idempotent).

    Preserves one citation per (entity, chunk) pair, so an entity mentioned
    across many chunks retains every mention rather than only the first.
    """
    stmt = (
        pg_insert(EntityMention)
        .values(entity_id=entity_id, chunk_id=chunk_id)
        .on_conflict_do_nothing(index_elements=["entity_id", "chunk_id"])
    )
    session.execute(stmt)


def store_extraction_results(
    session: Session, results: list[tuple[Chunk, ExtractionResult]]
) -> None:
    """Persist a batch of per-chunk extraction results into the graph tables.

    Consumes ``BatchResult.successes`` from :func:`app.extraction.batch.extract_batch`.
    For each chunk it upserts the extracted entities, records a mention linking
    each entity to the chunk, and upserts the relationships (resolving their
    string endpoints to entity IDs). Relationships whose endpoints were not
    extracted as entities from the same chunk are skipped rather than raised.
    """
    for chunk, result in results:
        # Map normalized entity name -> entity id, for resolving relationship endpoints.
        name_to_id: dict[str, UUID] = {}
        for extracted in result.entities:
            entity = upsert_entity(session, extracted.name, extracted.type)
            name_to_id[_normalize(extracted.name)] = entity.id
            _add_mention(session, entity.id, chunk.id)

        for rel in result.relationships:
            source_id = name_to_id.get(_normalize(rel.source))
            target_id = name_to_id.get(_normalize(rel.target))
            if source_id is None or target_id is None:
                # Dangling endpoint the model referenced but didn't extract as an
                # entity; skip rather than fabricate or crash the whole batch.
                continue
            upsert_relationship(session, source_id, target_id, rel.relation, chunk.id)

    session.commit()
