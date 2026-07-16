"""POST /query — answer a question with agentic hybrid retrieval.

Drives :class:`~app.retrieval.agent.RetrievalAgent`, which runs a bounded ReAct
loop over vector + graph tools and produces a grounded, citation-carrying answer.
The whole handler is timed for the ``latency_ms`` field.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.extraction.db.session import get_session
from app.retrieval.agent import RetrievalAgent

router = APIRouter()


class QueryRequest(BaseModel):
    question: str


@router.post("/query")
def query(body: QueryRequest, session: Session = Depends(get_session)) -> dict:
    # Plain ``def`` so FastAPI runs this blocking handler in its threadpool.
    start = time.perf_counter()
    try:
        result = RetrievalAgent(session).run(body.question)
    except ValueError as exc:
        # e.g. GEMINI_API_KEY unset — a configuration problem, not a bad request.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    latency_ms = (time.perf_counter() - start) * 1000

    return {
        "answer": result.answer,
        "citations": [{"type": c.kind, "id": c.id} for c in result.citations],
        "steps": len(result.steps),
        "latency_ms": latency_ms,
    }
