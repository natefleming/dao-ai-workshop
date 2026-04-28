# L300 -- Advanced

The third level of the DAO-AI workshop. L300 covers production-grade patterns that separate a working agent from a fast, accurate, scalable one, plus the alternate Python-construction path:

- **Lab 11 -- Instructed Retrieval.** Decompose natural-language queries into structured filter constraints, then layer cross-encoder + LLM-based reranking for precision. Pure ANN+rerank from Lab 6 isn't enough when users describe constraints (brand, price tier, project intent) inline.
- **Lab 12 -- Genie Context-Aware Caching.** Two-layer cache over a Genie tool: an L1 LRU exact-match cache and an L2 context-aware similarity cache. Cuts Genie API cost and latency dramatically for repeat / near-duplicate questions.
- **Lab 13 -- Programmatic Construction.** Build the same `AppConfig` in pure Python instead of YAML -- the entry point you reach for when generating agents dynamically (one per tenant, one per dataset) or embedding DAO-AI inside a larger Python application.

Lab 11 and Lab 12 reuse the products catalog from Lab 2 (extended with metadata for Lab 11) and a Genie Space pointed at it (for Lab 12). Lab 13 is concept-only -- no extra resources required.

## Walk this level in order

| Step | Path | Type | What it covers |
|---|---|---|---|
| 1 | [lab-11-instructed-retrieval/](lab-11-instructed-retrieval/) | Lab | Filter-aware retrieval with decomposition + cross-encoder + LLM rerank. |
| 2 | [lab-12-genie-caching/](lab-12-genie-caching/) | Lab | L1 LRU + L2 similarity caching over a Genie tool. |
| 3 | [lab-13-programmatic/](lab-13-programmatic/) | Lab | Build the same `AppConfig` from Python instead of YAML. |

## Prerequisites

L100 + L200 completed. You should be comfortable with:
- Loading DAO-AI configs with `AppConfig.from_file(path, params={...})`.
- Per-student deployment via `${var.username}` and `config.deploy_agent(target=DeploymentTarget.APPS)`.
- Lab 2 (UC tools) and Lab 6 (vector search + rerank) -- their data structures show up again here.
- Lab 7 (memory) -- chat-history summarization is covered there alongside Lakebase memory.

Lab-specific requirements:
- **Lab 11**: Vector Search endpoint, `databricks-claude-haiku-4-5` (decomposition + instruction rerank), `databricks-gte-large-en` (embedding).
- **Lab 12**: a Genie Space over the products table (Lab 3's space works), a SQL warehouse you can re-execute cached SQL on.

## What you'll have at the end

Two deployed Databricks Apps:
- `hardware-store-<your-username>` -- handles filter-rich, intent-laden product queries.
- `hardware-store-<your-username>` -- serves repeat / near-duplicate analytical questions from cache, falling through to Genie only on novel queries.

## Going deeper

- `dao-ai/config/examples/03_reranking/` -- more reranking recipes (instruction-aware reranking, hybrid stages).
- `dao-ai/config/examples/04_genie/` -- more cache patterns including the database-backed variant for multi-instance deployments, and a recipe for tuning cache hit-rate thresholds.
- `dao-ai/config/examples/15_complete_applications/` -- end-to-end production examples that combine many of these patterns.
