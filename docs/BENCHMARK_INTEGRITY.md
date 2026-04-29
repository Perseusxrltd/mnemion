# Benchmark Integrity

Mnemion benchmark claims must remain reproducible and metric-specific.

Rules:

- Do not compare systems unless they use the same metric, split, top-k, and evaluation target.
- Distinguish retrieval recall from QA accuracy, MRR, Hit@1, Recall@5, Recall@10, and NDCG.
- Label local toy A/B tests as local A/B tests, not external benchmark results.
- Disclose when a heuristic was tuned on known failures.
- Do not headline perfect or near-perfect scores unless commands, data assumptions, and result files are present.
- Avoid network-dependent tests in CI; benchmark data downloads belong in documented reproduction steps.

Current benchmark docs should be read as a reproduction guide and historical record, not as an unconditional competitive leaderboard. New results should include:

- command used;
- dataset source and version;
- metric definition;
- sample size;
- top-k;
- whether an LLM reranker was used;
- result artifact path.
