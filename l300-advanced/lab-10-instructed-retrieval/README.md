# Lab 10 -- Instructed Retrieval

**Level:** L300 (advanced)

## Goals

- Extend Lab 2's products table with metadata columns (`brand_name`, `price_tier`, `weight_lbs`) so retrieval has filter dimensions.
- Configure a `retrievers.<name>.instructed:` block: column schema + decomposition + LLM rerank instructions.
- Layer **two** rerank stages: cross-encoder (FlashRank) → LLM-based instruction rerank.
- Watch a query like *"Milwaukee power tools under $100 for cabinet refinishing"* get decomposed into structured filters + a residual semantic query.

## Deliverable

An `instructed-search-<your-username>` agent that handles filter-rich, intent-laden product queries -- the kind that pure ANN+rerank from Lab 6 couldn't disambiguate.

---

**Use case:** `hardware_store++` -- the products catalog from Lab 2, extended with rich metadata so the instructed retriever has filter dimensions to work with.

**dao-ai concept:** **Instructed retrieval** -- a single retriever block that bundles four pipeline stages:

1. **Query decomposition** -- a small/fast LLM (`databricks-claude-haiku-4-5`) extracts filter constraints from natural language. *"Milwaukee tools under $100"* → `{brand_name: MILWAUKEE, price < 100}` + residual semantic query.
2. **Hybrid ANN search** -- 50 candidates per subquery, merged with reciprocal rank fusion.
3. **Cross-encoder rerank (FlashRank)** -- `ms-marco-MiniLM-L-12-v2` promotes the most relevant 20.
4. **Instruction-aware LLM rerank** -- the same haiku LLM applies natural-language priorities you specify (boost project-fit products, demote out-of-tier items) → top 10.

All four stages are declarative -- no Python in the pipeline.

## Files

| File | Purpose |
|---|---|
| `instructed_search.yaml` | Full retriever pipeline + agent + app config. |
| `data/products_extended.sql` | Self-contained DDL: `DROP IF EXISTS` + `CREATE TABLE` with the full 10-column extended schema (`sku`, `product_name`, `category`, `description`, `price`, `in_stock`, `brand_name`, `price_tier`, `sku_prefix`, `weight_lbs`) + `INSERT` for 30 sample rows. |
| `notebook.py` | Provision the products table, build the index, test filter-heavy queries, deploy. |

## Prerequisites

- Vector Search endpoint enabled.
- `databricks-claude-sonnet-4-5` (primary), `databricks-claude-haiku-4-5` (decomposition + rerank), `databricks-gte-large-en` (embedding) endpoints enabled.

This lab is **self-contained** -- it creates its own products table and extends it. Lab 2 is not a hard prerequisite.

## Run

Open `notebook.py`. Set `catalog`. The notebook provisions the products table, extends it, builds the index, and runs two filter-heavy queries that exercise the decomposition + reranking stack.

Deployed app name: `instructed-search-<your-username>`.

## Next

[Lab 11 -- Genie Context-Aware Caching](../lab-11-genie-caching/) -- demonstrate the L1 LRU (exact match) and L2 similarity caches over a Genie tool.
