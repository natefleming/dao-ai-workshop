# Lab 11 -- Knowledge-base Retrieval with Lakebase Search

**Level:** L200

## Goals

- Declare a `databases:` resource for a Lakebase project and wire a `type: lakebase_search` retriever over a Postgres KB articles table.
- Understand when Lakebase is the right retrieval backend (existing UC-adjacent Postgres data, hybrid dense+lexical retrieval, low-latency point-lookups) versus AI Search.
- Compare retrieval quality across three configurations: ANN only -> HYBRID (adds BM25) -> HYBRID + FlashRank cross-encoder rerank.
- See how `lakebase_search` (dao-ai 0.1.105) reaches feature parity with `ai_search` -- same tool schema, same `rerank:` field, same `filters` shape -- while keeping data on your existing Lakebase Postgres instead of an AI Search index.

## Deliverable

A `kb_assistant` agent that answers `"How do I reset my password?"` and `"When do password reset links expire?"` by retrieving and citing rows from `kb_articles` -- backed by Lakebase, not AI Search.

---

**Use case:** `saas_helpdesk` -- a KB assistant that answers customer questions by searching a Postgres table already sitting inside a Lakebase project (no separate vector store to keep in sync with the source of truth).

**DAO-AI concept:** **Lakebase as a first-class retrieval backend.** The `lakebase_search` retriever uses the `lakebase_vector` extension for ANN, `lakebase_text` for BM25, and RRF-merges them for HYBRID -- exposing the same tool schema the LLM sees for `ai_search`, so agent code doesn't change when you switch backends.

## What you'll learn

- The `resources.databases:` + `retrievers.<name>.type: lakebase_search` blocks and how they compose with the `lakebase_vector` / `lakebase_text` Postgres extensions.
- How `query_type: ANN | BM25 | HYBRID` maps to Lakebase indexes (`lakebase_ann` on the vector column, `lakebase_bm25` on the tsvector column).
- Layering the same `rerank:` FlashRank pass on top of a Lakebase retriever -- identical field to Lab 6's `ai_search` version.
- Building the same agent from Python instead of YAML -- see the bonus `notebook_programmatic.py`.

## Files

| File | Purpose |
|---|---|
| `01_ann_only.yaml` | Step 1 -- minimal ANN over passage embeddings. |
| `02_hybrid.yaml` | Step 2 -- adds `tsvector_column` + `query_type: HYBRID` (ANN + BM25 via RRF). |
| `03_reranked.yaml` | Step 3 (final / deploy) -- HYBRID + FlashRank cross-encoder rerank. |
| `data/kb_articles.sql` | Postgres DDL: extensions, `kb_articles` table (with generated `passage_tsv`), `lakebase_ann` + `lakebase_bm25` indexes, 10 seed rows. |
| `notebook.py` | Walks the three configs against the same query and finishes with a local `agent.apredict(...)` chat. |
| `notebook_programmatic.py` | Bonus -- rebuilds the same agent from pure Python (no YAML), demonstrating YAML <-> Python parity. |

## Prerequisites

- A **Lakebase project** provisioned in the workspace (workspace-admin one-time setup).
- A **secret scope** in the workspace with three keys the retriever will read at runtime:
  - `SP_CLIENT_ID` -- OAuth client id for a service principal with Lakebase access
  - `SP_CLIENT_SECRET` -- matching client secret
  - `DATABRICKS_HOST` -- `https://<workspace>.cloud.databricks.com`
  (Widget defaults assume these key names; override per widget if your scope uses different keys.)
- The `databricks-gte-large-en` foundation-model embedding endpoint enabled.
- The `databricks-claude-sonnet-4-5` chat endpoint enabled.
- Access to the Databricks SQL editor connected to the Lakebase Postgres database (for running `data/kb_articles.sql`).

## Run

1. **Run the DDL.** Open `data/kb_articles.sql` in the Databricks SQL editor, connect to your Lakebase project's Postgres database, and execute the file. This creates the extensions, the `kb_articles` table, and the two indexes -- but leaves `embedding` NULL.
2. **Open `notebook.py`.** Set the `lakebase_project` and `secret_scope` widgets at the top. The notebook backfills the `embedding` column via the configured embedding endpoint (idempotent -- re-running only encodes rows with NULL embeddings), then walks the three configs against the same query so you can see how HYBRID reorders results vs. ANN and how FlashRank re-scores on top.
3. **(Optional) Run `notebook_programmatic.py`** to see the exact same agent built from Python instead of YAML.

Deployed app name (from `${var.username}` in the yaml): `kb-assistant-<your-username>`. Deployment is left as an optional step at the end of `notebook.py`.

## Next

- [Lab 6](../lab-06-vector-search/) -- the `ai_search` sibling of this lab. Same tool schema, same rerank field, Databricks AI Search backend.
- [Lab 11 (L300)](../../L300-advanced/lab-11-instructed-retrieval/) -- adds LLM query decomposition + instruction-aware rerank on top of the same retriever. Works uniformly on `lakebase_search` and `ai_search` in dao-ai 0.1.105+.
- [Lab 13 (L300)](../../L300-advanced/lab-13-programmatic/) -- the general treatment of programmatic construction (this lab's `notebook_programmatic.py` is a lakebase-specific slice).
- The full reference config set for `lakebase_search`: [`config/examples/21_lakebase_search/`](https://github.com/natefleming/dao-ai/tree/main/config/examples/21_lakebase_search/) in the dao-ai repo.

## Back to the workshop

[Workshop README](../../README.md) | [L200 Building Real Agents](../README.md)
