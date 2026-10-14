"""Compare two local model owners with one worker shared over pinned loopback TLS.

Uses an existing, pinned model cache offline and public synthetic text. Each
case starts fresh processes. Reported RAM excludes the database, desktop and
unrelated host processes; it is not a whole-product minimum specification.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import multiprocessing
from pathlib import Path
import platform
import subprocess
import tempfile
import time

import psutil

QUERY = "Which database stores the synthetic project acceptance decision?"
SOURCE = (
    "Project Cedar stores its synthetic acceptance decision in PostgreSQL. "
    "Le café conserve la source et la révision. 中文笔记。\n"
) * 110


def digest(value):
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def child(connection, mode, role, cache, profile, threads, directory):
    # Import after spawn: neither case inherits a loaded ONNX session.
    from mnemion.service.embeddings import LocalEmbedder
    from mnemion.service.model_broker import ModelBroker, SharedLocalEmbedder
    from mnemion.service.model_catalog import LOCAL_GENERATIONS
    from mnemion.service.model_registry import ModelRegistry

    model = None
    try:
        arguments = {"threads": threads, "offline": True, "generation": LOCAL_GENERATIONS[profile]}
        if mode == "shared" and role == "api":
            model = SharedLocalEmbedder(directory, cache, **arguments)
        else:
            model = LocalEmbedder(cache, **arguments)
        registry = ModelRegistry(model, {profile: model})
        with ExitStack() as stack:
            stack.callback(registry.close)
            if mode == "shared" and role == "worker":
                stack.enter_context(ModelBroker(registry, directory))
            began = time.perf_counter()
            if role == "worker":
                chunks = model.document(SOURCE)
                result = {
                    "chunks": len(chunks),
                    "source_tokens": model.token_count(SOURCE),
                    "vectors_and_spans_sha256": digest(
                        [[chunk.start, chunk.end, chunk.vector] for chunk in chunks]
                    ),
                }
            else:
                vector = model.query(QUERY)
                result = {"query_vector_sha256": digest(vector)}
                if mode == "shared":
                    assert model._model is None and model._tokenizer is None
            connection.send(
                {"ok": True, **result, "seconds": round(time.perf_counter() - began, 4)}
            )
            # Stay alive so the parent measures both processes at the same time.
            if connection.recv() != "stop":
                raise ValueError("Unexpected measurement command")
    except BaseException as error:
        connection.send({"ok": False, "error": type(error).__name__})
        raise
    finally:
        connection.close()


def receive(connection):
    if not connection.poll(180):
        raise RuntimeError("Model resource probe exceeded its 180 second operation deadline")
    result = connection.recv()
    if result.pop("ok") is not True:
        raise RuntimeError("Model resource probe failed: " + result["error"])
    return result


def measure(mode, cache, profile, threads, directory):
    context = multiprocessing.get_context("spawn")
    children, results = [], {}
    try:
        for role in ("worker", "api"):
            parent, receiver = context.Pipe()
            process = context.Process(
                target=child,
                args=(receiver, mode, role, cache, profile, threads, directory),
            )
            process.start()
            receiver.close()
            children.append((role, process, parent))
            results[role] = receive(parent)
        total = {}
        for role, process, _ in children:
            counters = psutil.Process(process.pid).memory_full_info()
            memory = {
                name + "_bytes": getattr(counters, name)
                for name in ("rss", "uss", "pss")
                if hasattr(counters, name)
            }
            results[role]["memory"] = memory
            for key, value in memory.items():
                total[key] = total.get(key, 0) + value
        results["total"] = total
        return results
    finally:
        for _, process, connection in reversed(children):
            if process.is_alive():
                try:
                    connection.send("stop")
                except (BrokenPipeError, EOFError):
                    pass
                process.join(10)
            if process.is_alive():
                process.terminate()
                process.join(5)
            connection.close()
            if process.is_alive():
                process.kill()
                process.join(5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--profile", choices=("e5-small", "bge-small-en"), default="e5-small")
    parser.add_argument("--threads", type=int, choices=range(1, 65), default=1)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="mnemion-model-resources-") as temporary:
        baseline = measure("separate", args.cache, args.profile, args.threads, Path(temporary))
        shared = measure("shared", args.cache, args.profile, args.threads, Path(temporary))
    assert baseline["api"]["query_vector_sha256"] == shared["api"]["query_vector_sha256"]
    assert (
        baseline["worker"]["vectors_and_spans_sha256"]
        == shared["worker"]["vectors_and_spans_sha256"]
    )
    from mnemion.service.model_catalog import LOCAL_GENERATIONS

    print(
        json.dumps(
            {
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "scope": "two isolated model processes; excludes database, desktop and other host processes",
                "source_base_commit": subprocess.check_output(
                    ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
                ).strip(),
                "source_files": {
                    name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                    for name in (
                        "mnemion/service/model_broker.py",
                        "mnemion/service/model_registry.py",
                        "mnemion/service/embeddings.py",
                        "benchmarks/shared_model_resources.py",
                    )
                },
                "platform": platform.system(),
                "architecture": platform.machine(),
                "python": platform.python_version(),
                "runtime_versions": {
                    name: importlib.metadata.version(name)
                    for name in ("fastembed", "onnxruntime", "tokenizers", "httpx")
                },
                "profile": args.profile,
                "generation_id": LOCAL_GENERATIONS[args.profile].id,
                "threads_per_model": args.threads,
                "source_sha256": hashlib.sha256(SOURCE.encode()).hexdigest(),
                "offline": True,
                "production_memory_writes": 0,
                "cloud_model_calls": 0,
                "baseline": baseline,
                "shared": shared,
                "savings_percent": {
                    key: round(100 * (value - shared["total"][key]) / value, 2)
                    for key, value in baseline["total"].items()
                    if value
                },
                "query_document_vectors_and_unicode_spans_identical": True,
                "api_keeps_no_local_model_or_tokenizer": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
