from functools import lru_cache

import numpy as np
from transformers import AutoTokenizer, AutoModel
from app.config import get_settings
import torch
    
@lru_cache(maxsize=1)
def get_embedder() -> tuple[AutoTokenizer, AutoModel]:
    settings = get_settings()
    model_name = settings.embedding_model_name
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    return tokenizer, model
    
def _mean_pool(last_hidden_state: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:

    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    return (last_hidden_state * mask).sum(1) / mask.sum(1).clamp(min=1e-9)

def _encode(texts: list[str]) -> np.ndarray:
    tokenizer, model = get_embedder()
    inputs = tokenizer(texts, padding=True, truncation=True, return_tensors="pt")
    
    """
    Input ids are the token ids for each input text
    Attention mask indicates which tokens are actual input (1) vs padding (0)
    Example:
    For the input texts ["Hello world!", "Hi"], the tokenizer might produce:
    inputs = {
        "input_ids": tensor([[15496, 995, 0], [31414, 0, 0]]),
        "attention_mask": tensor([[1, 1, 0], [1, 0, 0]])
    }
    - "Hello world!" is tokenized into [15496, 995] and padded with a 0 to match the length of the longest input
    - "Hi" is tokenized into [31414] and padded with two 0s
    """

    # We're only doing inference here — nothing in this function ever calls
    # .backward(). That means there's no reason for PyTorch to build an autogradient
    # graph or hold onto every intermediate tensor from the forward pass (which it
    # would do by default, in case a backward pass came later). no_grad() turns
    # that tracking off entirely, saving a meaningful amount of memory and time
    # since we're discarding the graph immediately anyway.
    with torch.no_grad():
        # Under the hood, model is a PyTorch model.
        # model(**inputs) unpacks the dict into input_ids=..., attention_mask=...
        # and runs a forward pass: input_ids flows through every layer of the
        # model, producing outputs.last_hidden_state — one vector per token.
        outputs = model(**inputs)

    # In Loom, each input_ids is a chunk that we pulled from our chunker.
    # In outputs = model(**inputs), each chunk is passed through the embedding model to get a vector for each token in the chunk.
    # To get a single vector for the whole chunk, we do mean pooling:
    # we take the mean of all the token vectors in the chunk, but only counting the real tokens (attention_mask=1) and ignoring padding (attention_mask=0).
    # The result is a single vector that represents the entire chunk, which we can then store in our database and use for similarity search.
    pooled = _mean_pool(outputs.last_hidden_state, inputs["attention_mask"])
    
    # Finally, we L2-normalize the pooled vectors. This is a common practice for embeddings, especially when using cosine similarity 
    # because it ensures that the length of the embedding vector doesn't affect similarity calculations
    # After normalization, the cosine similarity between two vectors is equivalent to their dot product
    # This can improve the performance of similarity search in our vector database
    normed = torch.nn.functional.normalize(pooled, p=2, dim=1) 

    return normed.numpy()

def embed(texts: list[str]) -> np.ndarray:
    return _encode(texts)

def embed_query(text: str) -> np.ndarray:
    prefixed = "Represent this sentence for searching relevant passages: " + text
    return _encode([prefixed])[0]