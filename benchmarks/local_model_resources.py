"""Measure the actual local document/query pipeline using public synthetic text.

Prepare the model cache first. No inference provider, database, user corpus or
credentials are used. These resource measurements are not a retrieval-quality
evaluation or a promise of production throughput.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import inspect
import json
from pathlib import Path
import platform
import time

import psutil

from mnemion.service.embeddings import LocalEmbedder
from mnemion.service.model_catalog import LOCAL_GENERATIONS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--profile", choices=sorted(LOCAL_GENERATIONS), default="e5-small")
    parser.add_argument("--threads", type=int, choices=range(1, 65), default=2)
    parser.add_argument("--allow-download", action="store_true")
    args = parser.parse_args()
    process = psutil.Process()
    paragraph = (
        "The memory service keeps source evidence and citations for project decisions. "
        "Les agents partagent les décisions du projet et conservent les sources originales. "
        "The team needs scoped access, reliable updates, and private source connections. "
        "Every correction preserves the previous revision and records the reason for the change.\n"
    )
    text = paragraph * 180
    started = time.perf_counter()
    model = LocalEmbedder(
        args.cache,
        threads=args.threads,
        offline=not args.allow_download,
        generation=LOCAL_GENERATIONS[args.profile],
    )
    model.prepare()
    preparation_seconds = time.perf_counter() - started
    loaded_rss = process.memory_info().rss
    started = time.perf_counter()
    query = model.query("How are source evidence and project decisions preserved?")
    query_seconds = time.perf_counter() - started
    started = time.perf_counter()
    chunks = model.document(text)
    document_seconds = time.perf_counter() - started
    after_rss = process.memory_info().rss
    fingerprint = json.dumps(
        {"query": query, "chunks": [[c.start, c.end, c.vector] for c in chunks]},
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    peak = None
    if platform.system() != "Windows":
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if platform.system() != "Darwin":
            peak *= 1024
    elif hasattr(process.memory_info(), "peak_wset"):
        peak = process.memory_info().peak_wset
    print(
        json.dumps(
            {
                "scope": "single_local_model_process_synthetic_document",
                "python": platform.python_version(),
                "platform": platform.system(),
                "architecture": platform.machine(),
                "runtime_versions": {
                    name: importlib.metadata.version(name)
                    for name in ("fastembed", "onnxruntime", "tokenizers")
                },
                "profile": args.profile,
                "implementation_sha256": hashlib.sha256(
                    Path(inspect.getfile(LocalEmbedder)).read_bytes()
                ).hexdigest(),
                "generation_id": model.generation.id,
                "model_threads": args.threads,
                "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "source_characters": len(text),
                "source_tokens": model.token_count(text),
                "chunks": len(chunks),
                "vectors_and_spans_sha256": hashlib.sha256(fingerprint).hexdigest(),
                "loaded_rss_bytes": loaded_rss,
                "post_document_rss_bytes": after_rss,
                "peak_rss_bytes": peak,
                "preparation_seconds": round(preparation_seconds, 4),
                "query_seconds": round(query_seconds, 4),
                "document_seconds": round(document_seconds, 4),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
