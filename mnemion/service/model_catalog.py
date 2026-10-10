"""Reviewed model choices; no download, inference, credentials or remote defaults.

The existing E5 fingerprint is retained. A model's popularity or vendor score is
not a Mnemion evaluation, so changing the default requires a separate comparison.
"""

from .embeddings import DEFAULT_GENERATION, Generation


BGE_SMALL_GENERATION = Generation(
    model="BAAI/bge-small-en-v1.5",
    dimensions=384,
    configuration={
        "repository": "Xenova/bge-small-en-v1.5",
        "revision": "ea104dacec62c0de699686887e3f920caeb4f3e3",
        "model_file": "onnx/model_quantized.onnx",
        "model_sha256": "6c9c6101a956d62dfb5e7190c538226c0c5bb9cb27b651234b6df063ee7dbfe4",
        "tokenizer_sha256": "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66",
        "runtime": "fastembed",
        "runtime_version": "0.9.0",
        "pooling": "cls",
        "normalization": "l2",
        "query_prefix": "Represent this sentence for searching relevant passages: ",
        "document_prefix": "",
        "chunk_tokens": 384,
        "overlap_tokens": 48,
        "max_query_tokens": 480,
        "offset_unit": "unicode_codepoints",
    },
)

LOCAL_GENERATIONS = {"e5-small": DEFAULT_GENERATION, "bge-small-en": BGE_SMALL_GENERATION}

MODEL_CATALOG = (
    {
        "id": "e5-small",
        "label": "Multilingual E5 Small",
        "model": DEFAULT_GENERATION.model,
        "execution": "local_cpu",
        "dimensions": 384,
        "languages": "multilingual",
        "license": "MIT",
        "source": "https://huggingface.co/intfloat/multilingual-e5-small",
        "description": "Current multilingual baseline, with a pinned quantized ONNX runtime.",
    },
    {
        "id": "bge-small-en",
        "label": "BGE Small English v1.5",
        "model": BGE_SMALL_GENERATION.model,
        "execution": "local_cpu",
        "dimensions": 384,
        "model_download_bytes": 34_014_426,
        "languages": "English",
        "license": "MIT",
        "source": "https://huggingface.co/BAAI/bge-small-en-v1.5",
        "description": "Small English-only CPU option. Download size is not a RAM requirement.",
    },
    {
        "id": "qwen3-embedding-0.6b",
        "label": "Qwen3 Embedding 0.6B",
        "model": "Qwen/Qwen3-Embedding-0.6B",
        "execution": "configured_endpoint",
        "dimensions": 1024,
        "languages": "multilingual",
        "license": "Apache-2.0",
        "source": "https://huggingface.co/Qwen/Qwen3-Embedding-0.6B",
        "description": "Use a separately operated Ollama or compatible model server; no client model download.",
    },
    {
        "id": "openai-embedding-3",
        "label": "OpenAI text-embedding-3",
        "model": "text-embedding-3-small / text-embedding-3-large",
        "execution": "configured_endpoint",
        "languages": "multilingual",
        "source": "https://developers.openai.com/api/docs/guides/embeddings",
        "description": "Optional metered cloud provider, with configurable dimensions. Requires operator credentials and space approval.",
    },
)
