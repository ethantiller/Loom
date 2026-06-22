from functools import lru_cache
import json

import numpy as np
import torch
from huggingface_hub import hf_hub_download
from safetensors.torch import load_file as load_safetensors
from transformers import AutoTokenizer, AutoModel, PreTrainedTokenizerBase

from app.config import get_settings


@lru_cache(maxsize=1)
def get_embedder() -> tuple[PreTrainedTokenizerBase, AutoModel, list[torch.nn.Linear]]:
    settings = get_settings()
    model_name = settings.embedding_model_name

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    model.eval()

    # AutoModel only loads the transformer backbone -- it has no idea the
    # repo also ships extra trained "Dense" projection layers (768 -> 3072
    # -> 768). Those live in their own small module folders (e.g.
    # "2_Dense/", "3_Dense/"). modules.json lists exactly which subfolders
    # hold them, so we don't have to guess folder names.
    modules_path = hf_hub_download(model_name, filename="modules.json")
    modules = json.load(open(modules_path))
    dense_subfolders = sorted(m["path"] for m in modules if "Dense" in m["type"])
    
    dense_layers: list[torch.nn.Linear] = []
    for subfolder in dense_subfolders:
        cfg_path = hf_hub_download(model_name, filename=f"{subfolder}/config.json")
        cfg = json.load(open(cfg_path))

        layer = torch.nn.Linear(
            cfg["in_features"], cfg["out_features"], bias=cfg.get("bias", False)
        )
        weights_path = hf_hub_download(model_name, filename=f"{subfolder}/model.safetensors")
        state_dict = load_safetensors(weights_path)
        # saved keys are "linear.weight" / "linear.bias" -- torch.nn.Linear
        # expects plain "weight" / "bias"
        state_dict = {k.replace("linear.", ""): v for k, v in state_dict.items()}
        layer.load_state_dict(state_dict)
        layer.eval()
        dense_layers.append(layer)

    return tokenizer, model, dense_layers


def _mean_pool(last_hidden_state: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    return (last_hidden_state * mask).sum(1) / mask.sum(1).clamp(min=1e-9)


def _encode(texts: list[str]) -> np.ndarray:
    tokenizer, model, dense_layers = get_embedder()
    inputs = tokenizer(texts, padding=True, truncation=True, return_tensors="pt")

    with torch.no_grad():
        outputs = model(**inputs)
        pooled = _mean_pool(outputs.last_hidden_state, inputs["attention_mask"])

        # Apply both learned Dense projection layers, in order: 768 -> 3072 -> 768.
        # This is the step our earlier hand-rolled version was missing -- it's
        # a *trained* transformation, not bookkeeping like the padding mask was.
        projected = pooled
        for dense in dense_layers:
            projected = dense(projected)

        normed = torch.nn.functional.normalize(projected, p=2, dim=1)

    return normed.numpy()


def embed(texts: list[str]) -> np.ndarray:
    # EmbeddingGemma's document-side prompt, per its model card.
    prefixed = [f"title: none | text: {t}" for t in texts]
    return _encode(prefixed)


def embed_query(text: str) -> np.ndarray:
    # EmbeddingGemma's query-side prompt -- deliberately different from the
    # document prompt. This asymmetry is what the model was trained with,
    # so queries and documents land correctly aligned in the same space.
    prefixed = f"task: search result | query: {text}"
    return _encode([prefixed])[0]