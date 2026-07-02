from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from google.genai import types as genai_types
from google.genai.errors import ClientError, ServerError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.extraction.db.models import Chunk
from app.extraction.extractor import EntityExtractor
from app.extraction.schemas import ExtractionResult

DEFAULT_CONCURRENCY = 5
MAX_ATTEMPTS = 3
RATE_LIMIT_CODE = 429

# Below this many chunks, run live concurrent calls for low latency. At or above
# it, submit a Gemini Batch API job, which is ~50% cheaper but async (minutes+).
BATCH_API_THRESHOLD = 10
BATCH_POLL_INTERVAL = 30.0

_TERMINAL_STATES = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_PARTIALLY_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
}
_SUCCESS_STATES = {"JOB_STATE_SUCCEEDED", "JOB_STATE_PARTIALLY_SUCCEEDED"}


class BatchJobError(Exception):
    """A chunk could not be extracted via the Batch API (job failed or no response)."""


def _is_transient(exc: BaseException) -> bool:
    """Retry on server-side errors (5xx) and rate limiting (429)."""
    if isinstance(exc, ServerError):
        return True
    if isinstance(exc, ClientError):
        return getattr(exc, "code", None) == RATE_LIMIT_CODE
    return False


@dataclass
class BatchResult:
    successes: list[tuple[Chunk, ExtractionResult]] = field(default_factory=list)
    failures: list[tuple[Chunk, Exception]] = field(default_factory=list)


async def extract_batch(
    chunks: list[Chunk],
    concurrency: int = DEFAULT_CONCURRENCY,
    *,
    extractor: EntityExtractor | None = None,
    batch_api_threshold: int = BATCH_API_THRESHOLD,
    poll_interval: float = BATCH_POLL_INTERVAL,
) -> BatchResult:
    """Extract entities from many chunks without letting one bad chunk abort the batch.

    For fewer than ``batch_api_threshold`` chunks, runs live ``generateContent`` calls
    concurrently (bounded by ``concurrency``) for low latency. At or above the
    threshold, submits a Gemini Batch API job, which is roughly half the cost but runs
    asynchronously. Either way, per-chunk failures land in :attr:`BatchResult.failures`
    so the caller can log/report them separately.
    """
    if not chunks:
        return BatchResult()

    extractor = extractor or EntityExtractor()

    if len(chunks) >= batch_api_threshold:
        return await _extract_via_batch_api(chunks, extractor, poll_interval)
    return await _extract_concurrently(chunks, extractor, concurrency)


async def _extract_concurrently(
    chunks: list[Chunk], extractor: EntityExtractor, concurrency: int
) -> BatchResult:
    semaphore = asyncio.Semaphore(concurrency)

    @retry(
        stop=stop_after_attempt(MAX_ATTEMPTS),
        wait=wait_exponential(multiplier=1, max=10),
        retry=retry_if_exception(_is_transient),
        reraise=True,
    )
    async def _extract_with_retry(chunk: Chunk) -> ExtractionResult:
        # extractor.extract issues a blocking network call; offload it so many
        # can run concurrently under the event loop.
        return await asyncio.to_thread(extractor.extract, chunk)

    async def _run(chunk: Chunk) -> ExtractionResult:
        async with semaphore:
            return await _extract_with_retry(chunk)

    outcomes = await asyncio.gather(*(_run(chunk) for chunk in chunks), return_exceptions=True)

    result = BatchResult()
    for chunk, outcome in zip(chunks, outcomes):
        if isinstance(outcome, Exception):
            result.failures.append((chunk, outcome))
        else:
            result.successes.append((chunk, outcome))
    return result


async def _extract_via_batch_api(
    chunks: list[Chunk], extractor: EntityExtractor, poll_interval: float
) -> BatchResult:
    client = extractor.client
    config = extractor.generation_config()
    requests = [
        genai_types.InlinedRequest(model=extractor.model, contents=chunk.text, config=config)
        for chunk in chunks
    ]

    job = await asyncio.to_thread(client.batches.create, model=extractor.model, src=requests)
    while _state_name(job.state) not in _TERMINAL_STATES:
        await asyncio.sleep(poll_interval)
        job = await asyncio.to_thread(client.batches.get, name=job.name)

    result = BatchResult()

    if _state_name(job.state) not in _SUCCESS_STATES:
        error = BatchJobError(f"batch job {job.name} ended in state {_state_name(job.state)}")
        result.failures.extend((chunk, error) for chunk in chunks)
        return result

    responses = (job.dest.inlined_responses if job.dest else None) or []
    for chunk, inlined in zip(chunks, responses):
        if inlined.error is not None:
            result.failures.append((chunk, _as_exception(inlined.error)))
            continue
        try:
            result.successes.append((chunk, extractor.parse_response(chunk.id, inlined.response)))
        except Exception as exc:  # noqa: BLE001 - a bad chunk must not abort the batch
            result.failures.append((chunk, exc))

    # Any chunks the service didn't return a response for are failures, not silent drops.
    for chunk in chunks[len(responses):]:
        result.failures.append((chunk, BatchJobError("no batch response returned")))

    return result


def _state_name(state: object) -> str:
    """JobState may be an enum or a bare string depending on transport; normalize to str."""
    return getattr(state, "name", None) or str(state)


def _as_exception(error: object) -> Exception:
    if isinstance(error, Exception):
        return error
    return BatchJobError(str(error))
