"""Evaluation harness for the Loom GraphRAG system (GRAG-20).

Runs two retrieval modes (vector-only and hybrid) against the hand-authored QA
set in ``app/eval/qa_set.json``, scores each mode on recall@k and answer
correctness, and reports results broken out by ``expected_hops`` bucket.

Usage (from the repo root):

    cd app
    uv run python -m app.eval.run_eval

Or add a ``make eval`` target. Requires:
- Postgres seeded (make seed or equivalent)
- GEMINI_API_KEY set for LLM-as-judge and for generate_answer

Output:
- Markdown comparison table printed to stdout
- app/eval/results.csv written (stdlib csv only — no pandas)

The definition of done is that on the hops >= 2 subset, hybrid recall@k >= vector-only
recall@k. If that does not hold, it signals that the corpus connectivity needs
revisiting (GRAG-19), not that the harness should be adjusted.
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports: keep the module importable even without a live DB/Gemini key
# (test discovery should not fail due to missing secrets).
# ---------------------------------------------------------------------------

QA_PATH = Path(__file__).parent / "qa_set.json"
RESULTS_PATH = Path(__file__).parent / "results.csv"

K = 5  # number of chunks to retrieve in each mode


def _load_qa() -> list[dict[str, Any]]:
    with QA_PATH.open() as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Retrieval helpers
# ---------------------------------------------------------------------------


def _vector_only_context(session, question: str, k: int):
    """Build a RetrievalContext using vector search only (no graph traversal)."""
    from app.ingestion.embedder import embed_query
    from app.ingestion.chunker import count_tokens
    from app.retrieval.hybrid import RetrievalContext
    from app.retrieval.vector_search import similarity_search

    embedding = embed_query(question)
    chunks = similarity_search(session, embedding, k)
    total_tokens = sum(c.token_count for c in chunks)
    return RetrievalContext(
        chunks=chunks,
        graph_facts="",
        total_tokens=total_tokens,
        entities={},
    )


def _hybrid_context(session, question: str, k: int):
    """Build a RetrievalContext using hybrid retrieval (vector + graph)."""
    from app.retrieval.hybrid import HybridRetriever

    return HybridRetriever(session).retrieve(question, k=k)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _score_entry(
    qa: dict[str, Any],
    session,
) -> dict[str, Any]:
    """Run both modes for one QA entry and return a flat result dict."""
    from app.retrieval.generator import generate_answer
    from app.eval.metrics import answer_correctness, recall_at_k

    question = qa["question"]
    expected = qa["expected_answer"]
    gold_entities = qa.get("gold_entities", [])
    hops = qa.get("expected_hops", 1)

    logger.info("Evaluating [hops=%d]: %s", hops, question[:80])

    # Vector-only
    vec_context = _vector_only_context(session, question, K)
    try:
        vec_answer_result = generate_answer(question, vec_context)
        vec_answer = vec_answer_result.answer
    except Exception as exc:  # noqa: BLE001
        logger.warning("vector generate_answer failed: %s", exc)
        vec_answer = ""

    vec_recall = recall_at_k(gold_entities, vec_context, session)
    vec_correct = answer_correctness(question, expected, vec_answer)

    # Hybrid
    hyb_context = _hybrid_context(session, question, K)
    try:
        hyb_answer_result = generate_answer(question, hyb_context)
        hyb_answer = hyb_answer_result.answer
    except Exception as exc:  # noqa: BLE001
        logger.warning("hybrid generate_answer failed: %s", exc)
        hyb_answer = ""

    hyb_recall = recall_at_k(gold_entities, hyb_context, session)
    hyb_correct = answer_correctness(question, expected, hyb_answer)

    return {
        "question": question,
        "expected_hops": hops,
        "vec_recall": vec_recall,
        "vec_correct": vec_correct,
        "hyb_recall": hyb_recall,
        "hyb_correct": hyb_correct,
    }


# ---------------------------------------------------------------------------
# Aggregation and reporting
# ---------------------------------------------------------------------------


def _aggregate(rows: list[dict], mode: str, hop_bucket: str) -> dict[str, Any]:
    """Aggregate metric values for a given mode and hop bucket."""
    if hop_bucket == "all":
        subset = rows
    else:
        min_hops = int(hop_bucket.split(">=")[1])
        subset = [r for r in rows if r["expected_hops"] >= min_hops]

    n = len(subset)
    if n == 0:
        return {"n": 0, "recall": "—", "correct": "—"}

    recall_key = f"{mode}_recall"
    correct_key = f"{mode}_correct"
    recall = sum(1 for r in subset if r[recall_key]) / n
    correct = sum(1 for r in subset if r[correct_key]) / n
    return {"n": n, "recall": f"{recall:.2f}", "correct": f"{correct:.2f}"}


def _print_table(rows: list[dict]) -> None:
    buckets = ["all", ">=2", ">=3"]
    modes = [("vector-only", "vec"), ("hybrid", "hyb")]

    header = "| Mode | Hop Bucket | N | Recall@k | Correctness |"
    sep =    "|------|------------|---|----------|-------------|"
    print()
    print(header)
    print(sep)
    for mode_label, mode_key in modes:
        for bucket in buckets:
            agg = _aggregate(rows, mode_key, bucket)
            print(
                f"| {mode_label} | {bucket} | {agg['n']} | "
                f"{agg['recall']} | {agg['correct']} |"
            )
    print()


def _write_csv(rows: list[dict]) -> None:
    buckets = ["all", ">=2", ">=3"]
    modes = [("vector-only", "vec"), ("hybrid", "hyb")]

    with RESULTS_PATH.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["mode", "hop_bucket", "n", "recall_at_k", "correctness"])
        for mode_label, mode_key in modes:
            for bucket in buckets:
                agg = _aggregate(rows, mode_key, bucket)
                writer.writerow(
                    [mode_label, bucket, agg["n"], agg["recall"], agg["correct"]]
                )
    logger.info("Results written to %s", RESULTS_PATH)


def _check_hypothesis(rows: list[dict]) -> None:
    """Warn if hybrid does not outperform vector-only on hops >= 2."""
    hops2 = [r for r in rows if r["expected_hops"] >= 2]
    if not hops2:
        logger.warning("No hops >= 2 entries to evaluate hypothesis.")
        return

    vec_recall = sum(1 for r in hops2 if r["vec_recall"]) / len(hops2)
    hyb_recall = sum(1 for r in hops2 if r["hyb_recall"]) / len(hops2)
    if hyb_recall >= vec_recall:
        logger.info(
            "✓ Hypothesis CONFIRMED: hybrid recall@k (%.2f) >= vector-only (%.2f) on hops >= 2",
            hyb_recall, vec_recall,
        )
    else:
        logger.warning(
            "✗ Hypothesis NOT MET: hybrid recall@k (%.2f) < vector-only (%.2f) on hops >= 2 — "
            "consider revisiting corpus connectivity (GRAG-19)",
            hyb_recall, vec_recall,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    from app.extraction.db.session import SessionLocal

    qa_entries = _load_qa()
    logger.info("Loaded %d QA entries from %s", len(qa_entries), QA_PATH)

    rows: list[dict] = []
    with SessionLocal() as session:
        for qa in qa_entries:
            try:
                result = _score_entry(qa, session)
                rows.append(result)
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to evaluate entry %r: %s", qa.get("question", "?"), exc)

    if not rows:
        logger.error("No results collected. Is the corpus seeded?")
        sys.exit(1)

    _print_table(rows)
    _write_csv(rows)
    _check_hypothesis(rows)


if __name__ == "__main__":
    main()
