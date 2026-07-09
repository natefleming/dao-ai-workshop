# Lab 11 -- Lakebase Search Retrieval

**Level:** L200

## Goals

- Wire a `type: lakebase_search` retriever over a Postgres KB articles table backed by **Lakebase**.
- Use `provision()` to idempotently create the extensions, table, and indexes -- no manual DDL.
- Understand when Lakebase is the right retrieval backend (existing UC-adjacent Postgres data, hybrid dense + BM25 in one call, low-latency point-lookups) versus AI Search.
- See how `lakebase_search` reaches feature parity with `ai_search` -- same tool schema, same `rerank:` field, same `filters` shape -- while keeping data on your existing Lakebase Postgres.

## Deliverable

A `kb_assistant` agent that answers `"How do I reset my password?"` by retrieving and citing rows from `kb_articles` -- backed by Lakebase, using HYBRID (ANN + BM25) retrieval with FlashRank reranking.

---

**Use case:** `saas_helpdesk` -- a KB assistant that answers customer questions by searching a Postgres table already sitting inside a Lakebase project (no separate vector store to keep in sync with the source of truth).

**DAO-AI concept:** **Lakebase as a first-class retrieval backend.** The `lakebase_search` retriever uses the `lakebase_vector` extension for ANN, `lakebase_text` for BM25, and RRF-merges them for HYBRID -- exposing the same tool schema the LLM sees for `ai_search`, so agent code doesn't change when you switch backends.

## Files

| File | Purpose |
|---|---|
| `kb_assistant.yaml` | Retriever + agent config (HYBRID + FlashRank rerank). |
| `data/kb_articles.seed.sql` | 10 seed rows across three categories. Schema is created by `provision()` in the notebook. |
| `notebook.py` | The lab -- provision, seed, backfill embeddings, retrieve. |
| `notebook_programmatic.py` | Bonus -- same agent built from Python (no YAML). |

## Prerequisites

- A **Lakebase project** in the workspace (workspace-admin one-time setup).
- A **secret scope** with `DAO_AI_SP_CLIENT_ID` + `DAO_AI_SP_CLIENT_SECRET` (default scope name: `dao_ai_workshop`). The workshop's `setup/create_service_principal.py` and `setup/grant_lakebase_superuser.py` handle the creation -- see [Lab 7 README](../lab-07-memory/README.md#prerequisites).
- The `databricks-gte-large-en` (embedding) and `databricks-claude-sonnet-4-5` (chat) foundation-model endpoints.

## Run

Open `notebook.py`. Confirm the `lakebase_project` and `sp_secret_scope` widgets match your workspace, then run top-to-bottom. The notebook provisions the extensions + table + indexes, seeds 10 rows, backfills their embeddings, and retrieves against the final HYBRID + reranked config.

Optionally run `notebook_programmatic.py` to see the same agent built from Python instead of YAML.

## Next

- [Lab 6](../lab-06-vector-search/) -- the `ai_search` sibling of this lab. Same tool schema, Databricks AI Search backend.
- [Lab 11 (L300)](../../L300-advanced/lab-11-instructed-retrieval/) -- adds LLM query decomposition + instruction-aware rerank on top of the same retriever (works uniformly on `lakebase_search` and `ai_search` in dao-ai 0.1.106+).
- [Lab 13 (L300)](../../L300-advanced/lab-13-programmatic/) -- the general treatment of programmatic construction.
- The full reference config set for `lakebase_search`: [`config/examples/21_lakebase_search/`](https://github.com/natefleming/dao-ai/tree/main/config/examples/21_lakebase_search/).

## Back to the workshop

[Workshop README](../../README.md) | [L200 Building Real Agents](../README.md)
