# Lab 6 -- Knowledge-base Retrieval with Vector Search

**Level:** L200

## Goals

- Declare a `vector_stores:` resource with Delta Sync over a KB articles table.
- Configure a `retrievers:` block with ANN search parameters.
- Layer a FlashRank cross-encoder reranker on top of ANN for precision (50 candidates → top 5).
- Compare retrieval quality across three steps: ungrounded baseline → ANN → ANN+rerank.
- Run the index **on behalf of the calling user** (`on_behalf_of_user: true`) so the agent only ever returns rows the user has UC SELECT permission on -- a one-line config switch that turns a shared KB into a permission-aware one.

## Deliverable

A `kb-search` agent that answers `"How do I rotate my API keys without downtime?"` by retrieving and citing the matching KB article.

---

**Use case:** `saas_helpdesk` -- a `kb_assistant` that answers customer questions by retrieving the relevant KB articles via semantic similarity, then reranking for precision.

**DAO-AI concept:** **Vector store + retriever + factory tool.** Plus a **cross-encoder reranker** layered on top for precision.

## What you'll learn

- The `resources.vector_stores:`, `retrievers:`, and `tools.<name>.function.type: factory` (with `dao_ai.tools.create_vector_search_tool`) blocks.
- How `retriever.rerank:` wires a FlashRank cross-encoder on top of ANN. Pattern: ANN gives **recall** (50 candidates), rerank gives **precision** (top 5).
- Delta Sync vector indexes -- the index auto-rebuilds when the source table changes.

## Files

| File | Purpose |
|---|---|
| `01_kb_assistant.yaml` | Step 1 -- baseline (no retrieval, agent confabulates). |
| `02_kb_assistant_with_search.yaml` | Step 2 -- adds ANN retrieval. |
| `03_kb_assistant_with_reranking.yaml` | Step 3 (final / deploy) -- adds cross-encoder rerank. |
| `data/kb_articles.sql` | Seed SQL for the KB articles table. |
| `notebook.py` | Walk steps in turn so you can compare retrieval quality. |

## Prerequisites

- A Vector Search endpoint (default `dao_ai_workshop_vs`).
- `databricks-gte-large-en` foundation-model endpoint enabled.
- A Unity Catalog catalog you can create schemas in.

## Run

Open `notebook.py`. Set `catalog` widget. **First-run provisioning takes 5-10 minutes** as the index builds; subsequent runs are fast.

Deployed app name: `saas-helpdesk-<your-username>`.

## Next

[Chapter 7](../lab-7-memory/) -- give the support agent persistent memory so returning customers don't have to repeat themselves.
