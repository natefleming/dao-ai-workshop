# Lab 12 -- Genie Context-Aware Caching

**Level:** L300 (advanced)

## Goals

- Wrap a Genie Space with **two** layers of caching: an L1 LRU exact-match cache and an L2 context-aware similarity cache.
- Watch L1 hit on identical repeat questions (sub-millisecond).
- Watch L2 hit on near-duplicate questions (similarity-based).
- Understand why the cache stores the **SQL** (not the answer) and re-executes it on each hit.

## Deliverable

A `hardware-store-<your-username>` agent where the same analytical question runs in `O(seconds)` on the first call and `O(milliseconds)` on the second/third (L1 hit), and a re-phrasing of the question is also served from cache (L2 hit).

---

**Use case:** `hardware_store` -- a products analyst over Lab 2's catalog. The DAO-AI concept is what's interesting here, not the data.

**DAO-AI concept:** **Two-layer caching** over a Genie tool, configured entirely via the `args:` block of `dao_ai.tools.create_genie_toolkit`.

```
user question
    │
    ├──► L1: LRU cache (exact-match)
    │       hit?  → re-execute cached SQL on the warehouse → result
    │
    └──► L2: in-memory context-aware cache (similarity)
            hit?  → re-execute cached SQL → result
            miss? → call Genie API → cache the SQL → result
```

| Layer | What it matches on | Hit speed | When it helps |
|---|---|---|---|
| **L1 LRU** | Exact-match input string (after normalization) | Sub-millisecond | A user / dashboard / bot asks the same question repeatedly. |
| **L2 Context-aware** | Question embedding similarity (default ≥ 0.85) **AND** conversation-context similarity (default ≥ 0.80) over the last 3 turns | Tens of milliseconds (one embedding + cosine) | Near-duplicates that L1 misses, e.g. *"Give me the count of products in each category"* vs *"How many products do we have per category?"*. |

The cache stores the **generated SQL**, not the answer. On a hit, the SQL is re-executed against the warehouse so the data is always fresh -- only the question→SQL step is reused.

## Files

| File | Purpose |
|---|---|
| `cached_analyst.yaml` | Agent + Genie tool with both cache layers configured. |
| `notebook.py` | L1 demo (3× same question), L2 demo (rephrasings), tuning notes, deploy. |

## Prerequisites

- A Databricks Genie Space pointed at the products table (can reuse Lab 3's space).
- A SQL warehouse you can re-execute SQL against -- the cache replays SQL on hits.
- `databricks-claude-sonnet-4-5` (primary), `databricks-gte-large-en` (L2 embedding) endpoints enabled.

## Run

Open `notebook.py`. Set `genie_space_id` and `warehouse_id` widgets. The notebook walks L1 hits, then L2 hits, then deploys.

Deployed app name: `hardware-store-<your-username>`.

## In-memory vs. database-backed

This lab uses DAO-AI's **in-memory** L2 cache variant -- no external database required. Cache state is per-process; in a multi-instance app deployment each replica has its own cache.

For multi-instance deployments where you want a shared cache, swap `in_memory_context_aware_cache_parameters` for `context_aware_cache_parameters` and add a `database:` reference (Lakebase or external Postgres). See `dao-ai/config/examples/04_genie/genie_context_aware_cache.yaml` for the database-backed shape.

## Next

You're done with the workshop. See [`L300-advanced/README.md`](../README.md) for production-deployment guidance.
