import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extraction.db.models import Chunk


def similarity_search(session: Session, query_embedding: np.ndarray, k: int = 5) -> list[Chunk]:
    rows = session.execute(
        select(Chunk)
        .order_by(Chunk.embedding.cosine_distance(query_embedding))
        .limit(k)
    ).scalars().all()
    return list(rows)
