from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel
from transformers import AutoTokenizer, PreTrainedTokenizerBase

from ingestion.loaders import RawDocument


class ChunkResult(BaseModel):
    """Intermediate representation of a chunk before embedding and DB persistence."""
    source_path: Path
    ordinal: int
    text: str
    token_count: int
    start_token_idx: int
    end_token_idx: int

# Cache tokenizers to avoid re-loading them for every document chunking operation. 
@lru_cache(maxsize=1)
def _get_tokenizer(model_name: str) -> PreTrainedTokenizerBase:
    return AutoTokenizer.from_pretrained(model_name)


def chunk_document(
    doc: RawDocument, # the raw document to be chunked
    chunk_size: int, # the maximum number of tokens in each chunk
    chunk_overlap: int, # the number of tokens that overlap between consecutive chunks, must be less than chunk_size
    model_name: str, # the name of the model whose tokenizer should be used, e.g. "google/embeddinggemma-300m"
) -> list[ChunkResult]:
    if chunk_overlap >= chunk_size:
        raise ValueError(f"chunk_overlap ({chunk_overlap}) must be less than chunk_size ({chunk_size})")

    tokenizer = _get_tokenizer(model_name)
    
    # Tokenize the document, token_ids is a list of integers representing the tokenized input text. 
    # E.g., the text "Hello world!" might be tokenized into [15496, 995], where 15496 is the token ID for "Hello" and 995 is the token ID for "world".
    # This is because the tokenizer converts the raw text into a format that can be processed by the embedding model
    # It is important to use the same tokenizer as the embedding model to ensure that the tokenization is consistent with what the model expects
    token_ids: list[int] = tokenizer(
        doc.text, add_special_tokens=False, return_attention_mask=False
    )["input_ids"]

    if not token_ids:
        return []

    # Stride is the number of tokens to move forward for the next chunk
    stride = chunk_size - chunk_overlap
    starts = range(0, len(token_ids), stride)
    chunks: list[ChunkResult] = []

    # Chunk index is the number of the chunk in the sequence of chunks 
    # Starting token is the index of the first token in the chunk
    for chunk_index, starting_token in enumerate(starts):
        end = starting_token + chunk_size
        window = token_ids[starting_token:end]
        text = tokenizer.decode(window, skip_special_tokens=True)
        chunks.append(ChunkResult(
            source_path=doc.source_path,
            ordinal=chunk_index,
            text=text,
            token_count=len(window),
            start_token_idx=starting_token,
            end_token_idx=starting_token + len(window),
        ))
        if end >= len(token_ids):
            break

    return chunks
