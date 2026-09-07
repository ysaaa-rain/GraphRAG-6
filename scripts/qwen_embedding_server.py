"""Serve local Qwen3-Embedding through a small OpenAI-compatible API."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer


MODEL_ID = os.getenv("GRAPHRAG_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")
REVISION = os.getenv("GRAPHRAG_EMBEDDING_REVISION", "").strip()
DEVICE = os.getenv("GRAPHRAG_EMBEDDING_DEVICE", "cpu")
NORMALIZE = os.getenv("GRAPHRAG_EMBEDDING_NORMALIZE", "false").lower() == "true"
DIMENSION = int(os.getenv("GRAPHRAG_EMBEDDING_DIMENSION", "1024"))
PORT = int(os.getenv("GRAPHRAG_EMBEDDING_PORT", "8000"))

model_kwargs: dict[str, Any] = {"device": DEVICE}
if REVISION and not REVISION.startswith("待"):
    model_kwargs["revision"] = REVISION

model = SentenceTransformer(MODEL_ID, **model_kwargs)
app = FastAPI(title="GraphRAG local Qwen embedding service")


class EmbeddingRequest(BaseModel):
    model: str | None = None
    input: str | list[str]
    encoding_format: str | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "model": MODEL_ID,
        "revision": REVISION or None,
        "device": DEVICE,
        "dimension": DIMENSION,
        "normalize": NORMALIZE,
    }


@app.get("/v1/models")
def models() -> dict[str, Any]:
    return {"object": "list", "data": [{"id": MODEL_ID, "object": "model"}]}


@app.post("/v1/embeddings")
def embeddings(request: EmbeddingRequest) -> dict[str, Any]:
    inputs = [request.input] if isinstance(request.input, str) else request.input
    if not inputs or any(not isinstance(item, str) or not item.strip() for item in inputs):
        raise HTTPException(status_code=400, detail="input must contain non-empty text")
    vectors = model.encode(
        inputs,
        normalize_embeddings=NORMALIZE,
        convert_to_numpy=True,
        truncate_dim=DIMENSION,
        show_progress_bar=False,
    )
    data = [
        {"object": "embedding", "index": index, "embedding": vector.tolist()}
        for index, vector in enumerate(vectors)
    ]
    return {
        "object": "list",
        "data": data,
        "model": request.model or MODEL_ID,
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT)
