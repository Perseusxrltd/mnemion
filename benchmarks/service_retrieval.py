"""Reproducible LongMemEval retrieval evaluation through the real service API.

Use a dedicated disposable organization. Ingestion reads only historical session
IDs, dates and messages. Questions and answer labels enter scoring after all
records have been indexed. This reports retrieval, not generated-answer accuracy.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import random
import statistics
import time
from pathlib import Path

from mnemion.sdk import Client


def session_documents(sessions: list, identifiers: list, dates: list) -> list[dict]:
    """Keep all speakers and text; split large sessions without inferred facts."""
    if not len(sessions) == len(identifiers) == len(dates):
        raise ValueError("Session IDs, dates and histories must align")
    result = []
    for index, (session, identifier, date) in enumerate(
        zip(sessions, identifiers, dates, strict=True)
    ):
        turns = []
        for turn in session:
            content = turn.get("content")
            if not isinstance(content, str):
                raise ValueError("Benchmark messages must contain text")
            turns.append(f"[{turn['role']}]\n{content}")
        text = f"Conversation recorded: {date}\n\n" + "\n\n".join(turns)
        for offset in range(0, len(text), 48000):
            result.append(
                {
                    "key": f"{index}:{offset}",
                    "session_id": str(identifier),
                    "content": text[offset : offset + 48000],
                    "date": str(date),
                    "offset": offset,
                }
            )
    return result


def retrieval_metrics(ranked_sessions: list[str], relevant: set[str], cutoff: int) -> dict:
    if not relevant:
        return {"recall": None, "ndcg": None, "mrr": None, "complete": None}
    seen, dcg, reciprocal = set(), 0.0, 0.0
    for position, session in enumerate(ranked_sessions[:cutoff], 1):
        if session in relevant and session not in seen:
            dcg += 1 / math.log2(position + 1)
            if not reciprocal:
                reciprocal = 1 / position
        seen.add(session)
    ideal = sum(
        1 / math.log2(position + 1) for position in range(1, min(cutoff, len(relevant)) + 1)
    )
    found = seen & relevant
    return {
        "recall": len(found) / len(relevant),
        "ndcg": dcg / ideal,
        "mrr": reciprocal,
        "complete": found == relevant,
    }


def _write(path: Path, value) -> None:
    staged = path.with_suffix(path.suffix + ".pending")
    staged.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    staged.chmod(0o600)
    staged.replace(path)


def ingest(client: Client, row: dict, folder: Path, dataset_hash: str, workers: int) -> dict:
    qid = str(row["question_id"])
    documents = session_documents(
        row["haystack_sessions"], row["haystack_session_ids"], row["haystack_dates"]
    )
    digest = hashlib.sha256(json.dumps(documents, sort_keys=True).encode()).hexdigest()
    path = folder / (hashlib.sha256(qid.encode()).hexdigest() + ".json")
    if path.exists():
        state = json.loads(path.read_text(encoding="utf-8"))
        if state["dataset_hash"] != dataset_hash or state["documents_hash"] != digest:
            raise ValueError("Saved run inputs changed; use a new evaluation directory")
    else:
        space = client.request("POST", "/v1/spaces", body={"name": "LongMemEval " + qid})
        state = {
            "space_id": space["id"],
            "question_id": qid,
            "dataset_hash": dataset_hash,
            "documents_hash": digest,
            "receipts": [],
        }
        _write(path, state)
    if len(state["receipts"]) == len(documents):
        return state

    def save(document):
        key = hashlib.sha256((dataset_hash + qid + document["key"]).encode()).hexdigest()
        started = time.perf_counter()
        receipt = client.save(
            state["space_id"],
            document["content"],
            subject="Conversation history",
            metadata={
                "dataset": "longmemeval-s-cleaned",
                "session_id": document["session_id"],
                "recorded_date": document["date"],
                "session_offset": document["offset"],
            },
            source={
                "title": "Conversation " + document["session_id"],
                "content": document["content"],
            },
            idempotency_key="evaluation-" + key,
        )
        return {
            "memory_id": receipt.memory_id,
            "operation_id": receipt.operation_id,
            "session_id": document["session_id"],
            "content_hash": hashlib.sha256(document["content"].encode()).hexdigest(),
            "save_seconds": time.perf_counter() - started,
        }

    with ThreadPoolExecutor(max_workers=workers) as executor:
        state["receipts"] = list(executor.map(save, documents))
    _write(path, state)
    return state


def wait_indexed(client: Client, states: list[dict], timeout: float) -> float:
    started = time.perf_counter()
    deadline = time.monotonic() + timeout
    pending = {record["operation_id"] for state in states for record in state["receipts"]}
    while pending:
        for operation_id in list(pending):
            operation = client.operation(operation_id)
            if operation["state"] == "ready":
                pending.remove(operation_id)
            elif operation["state"] in {"failed", "cancelled"}:
                raise RuntimeError("Evaluation indexing did not complete successfully")
        if pending:
            if time.monotonic() >= deadline:
                raise TimeoutError("Evaluation indexing exceeded its declared time budget")
            time.sleep(1)
    return time.perf_counter() - started


def evaluate(
    client: Client, row: dict, state: dict, folder: Path, timeout: float, *, mode: str = "hybrid"
) -> dict:
    waited = wait_indexed(client, [state], timeout)
    mapping = {r["memory_id"]: r for r in state["receipts"]}
    relevant = set(map(str, row["answer_session_ids"])) & set(map(str, row["haystack_session_ids"]))
    # LongMemEval marks abstention cases in the question ID. These can retain
    # a related session ID even though that session does not contain an answer.
    unanswerable = str(row["question_id"]).endswith("_abs")
    if unanswerable:
        relevant = set()
    elif not relevant:
        raise ValueError("Answerable evaluation case has no gold session in its history")
    result = {
        "question_id": str(row["question_id"]),
        "category": row["question_type"],
        "mode": mode,
        "unanswerable": unanswerable,
        "records": len(mapping),
        "index_wait_seconds": waited,
        "metrics": {},
    }
    for cutoff in (5, 10, 20):
        started = time.perf_counter()
        response = client.search(row["question"], [state["space_id"]], limit=cutoff, mode=mode)
        seconds = time.perf_counter() - started
        if response.warnings and "semantic_index_incomplete" in response.warnings:
            raise RuntimeError("A measured query did not have a complete semantic index")
        ranked = []
        for hit in response.hits:
            if hit.space_id != state["space_id"] or hit.memory_id not in mapping:
                raise AssertionError("Retrieval crossed its evaluation scope")
            source = client.source(hit.evidence.source_revision_id)
            memory = client.fetch(hit.memory_id)
            if memory.content_hash != mapping[hit.memory_id]["content_hash"]:
                raise AssertionError("Canonical source content changed during evaluation")
            if source.content[hit.evidence.start : hit.evidence.end][:4000] != hit.evidence.excerpt:
                raise AssertionError("Source citation does not identify the reported evidence")
            if memory.content[hit.memory_span.start : hit.memory_span.end] != hit.text:
                raise AssertionError("Retrieved text does not match its memory offsets")
            ranked.append(mapping[hit.memory_id]["session_id"])
        result["metrics"][str(cutoff)] = {
            **retrieval_metrics(ranked, relevant, cutoff),
            "latency_seconds": seconds,
            "returned": len(ranked),
            "citations_validated": len(ranked),
        }
    # Save the actual bounded context for a separately declared answering model.
    context = client.request(
        "POST",
        "/v1/context",
        body={
            "query": row["question"],
            "space_ids": [state["space_id"]],
            "limit": 20,
            "token_budget": 4096,
            "mode": mode,
        },
    )
    context_sessions = []
    for citation in context.get("citations", []):
        if citation["space_id"] != state["space_id"] or citation["memory_id"] not in mapping:
            raise AssertionError("Context crossed its evaluation scope")
        context_sessions.append(mapping[citation["memory_id"]]["session_id"])
    result["context"] = {
        **retrieval_metrics(context_sessions, relevant, 20),
        "citations": len(context_sessions),
        "tokens": context.get("token_count", 0),
    }
    _write(
        folder
        / (hashlib.sha256(str(row["question_id"]).encode()).hexdigest() + f".{mode}.context.json"),
        {
            "question_id": result["question_id"],
            "question": row["question"],
            "question_date": row["question_date"],
            "context": context,
        },
    )
    return result


def mean_interval(values: list[float]) -> list[float] | None:
    """Fixed-seed 95% percentile bootstrap over questions; not a population guarantee."""
    if not values:
        return None
    rng = random.Random(20261009)
    samples = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(2000))
    return [samples[49], samples[1949]]


def summarize(results: list[dict]) -> dict:
    output = {
        "questions": len(results),
        "unanswerable": sum(r["unanswerable"] for r in results),
        "groups": {},
    }
    for category in ["all", *sorted({r["category"] for r in results})]:
        subset = [r for r in results if category == "all" or r["category"] == category]
        metrics = {}
        for cutoff in ("5", "10", "20"):
            values = [r["metrics"][cutoff] for r in subset]
            answerable = [v for v in values if v["recall"] is not None]
            latencies = sorted(v["latency_seconds"] for v in values)
            metrics[cutoff] = {
                "recall": statistics.mean(v["recall"] for v in answerable) if answerable else None,
                "ndcg": statistics.mean(v["ndcg"] for v in answerable) if answerable else None,
                "mrr": statistics.mean(v["mrr"] for v in answerable) if answerable else None,
                "recall_ci95": mean_interval([v["recall"] for v in answerable]),
                "complete_evidence": statistics.mean(v["complete"] for v in answerable)
                if answerable
                else None,
                "p50_seconds": statistics.median(latencies),
                "p95_seconds": latencies[math.ceil(len(latencies) * 0.95) - 1],
            }
        contexts = [r["context"] for r in subset if not r["unanswerable"]]
        output["groups"][category] = {
            "questions": len(subset),
            "cutoffs": metrics,
            "context_recall": statistics.mean(c["recall"] for c in contexts) if contexts else None,
            "context_complete": statistics.mean(c["complete"] for c in contexts)
            if contexts
            else None,
        }
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--split", choices=("development", "held_out"), required=True)
    parser.add_argument("--mode", choices=("hybrid", "lexical", "semantic"), default="hybrid")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--index-timeout", type=float, default=1800)
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 32:
        parser.error("Use 1–32 ingestion workers")
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    with args.dataset.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    if digest != plan["dataset_sha256"]:
        raise ValueError("Dataset hash does not match the frozen evaluation plan")
    credentials = json.loads(args.credentials.read_text(encoding="utf-8"))
    rows = {str(row["question_id"]): row for row in json.loads(args.dataset.read_bytes())}
    folder = args.state_dir / args.split
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest = {
        "dataset_sha256": digest,
        "plan_sha256": hashlib.sha256(args.plan.read_bytes()).hexdigest(),
        "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "ingestion_workers": args.workers,
        "index_timeout": args.index_timeout,
        "mode": args.mode,
    }
    manifest_path = folder / f"run-manifest-{args.mode}.json"
    if manifest_path.exists() and json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
        raise ValueError(
            "Evaluation configuration changed; preserve these results and use a new directory"
        )
    if not manifest_path.exists():
        _write(manifest_path, manifest)
    results, states = [], {}
    with Client(
        credentials.get("api_url", "http://127.0.0.1:7892"), credentials["api_key"], timeout=60
    ) as client:
        # Complete ingestion before reading question text in the measured path.
        for qid in plan[args.split]:
            states[qid] = ingest(client, rows[qid], folder, digest, args.workers)
            print(
                json.dumps({"ingested_question": qid, "records": len(states[qid]["receipts"])}),
                flush=True,
            )
        waited = wait_indexed(client, list(states.values()), args.index_timeout)
        print(json.dumps({"all_indexed": True, "index_wait_seconds": waited}), flush=True)
        for qid in plan[args.split]:
            result_path = folder / (
                hashlib.sha256(qid.encode()).hexdigest() + f".{args.mode}.result.json"
            )
            if result_path.exists():
                result = json.loads(result_path.read_text(encoding="utf-8"))
            else:
                result = evaluate(
                    client, rows[qid], states[qid], folder, args.index_timeout, mode=args.mode
                )
                _write(result_path, result)
            results.append(result)
            _write(
                folder / f"results-{args.mode}.json",
                {
                    "dataset_sha256": digest,
                    "plan": plan,
                    "results": results,
                    "summary": summarize(results),
                },
            )
            print(
                json.dumps(
                    {"evaluated_question": qid, "recall20": result["metrics"]["20"]["recall"]}
                ),
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
