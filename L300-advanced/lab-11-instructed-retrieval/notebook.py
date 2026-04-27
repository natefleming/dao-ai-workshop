# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 11 -- Instructed Retrieval
# MAGIC
# MAGIC **Level:** L300 (advanced)
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Extend Lab 2's products table with metadata columns (`brand_name`, `price_tier`, `weight_lbs`) so retrieval has filter dimensions.
# MAGIC - Configure a `retrievers.<name>.instructed:` block: column schema + decomposition + LLM rerank instructions.
# MAGIC - Layer **two** rerank stages: cross-encoder (FlashRank) → LLM-based instruction rerank.
# MAGIC - Watch a query like *"Milwaukee power tools under $100 for cabinet refinishing"* get decomposed into structured filters + a residual semantic query.
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC An `instructed-search-<your-username>` agent that handles filter-rich, intent-laden product queries -- the kind that pure ANN+rerank from Lab 6 couldn't disambiguate.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 -- Install dependencies

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.60" databricks-vectorsearch
# MAGIC %restart_python

# COMMAND ----------

from importlib.metadata import version

print(f"dao-ai={version('dao-ai')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 -- Configure parameters

# COMMAND ----------

import re

from databricks.sdk import WorkspaceClient
from langgraph.graph.state import CompiledStateGraph
from typing import Any

w: WorkspaceClient = WorkspaceClient()
short_name: str = w.current_user.me().user_name.split("@")[0].lower()
username: str = re.sub(r"[^a-z0-9]+", "-", short_name).strip("-")[:13]
print(f"Derived username: {username}")

dbutils.widgets.text("catalog", "", "Catalog (e.g. workshop_jane_doe)")
dbutils.widgets.text("schema", "dao_ai", "Schema")
dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-4-5", "LLM endpoint")
dbutils.widgets.text("decomposition_llm_endpoint", "databricks-claude-haiku-4-5", "Decomposition / rerank LLM")
dbutils.widgets.text("embedding_model", "databricks-gte-large-en", "Embedding endpoint")
dbutils.widgets.text("vector_search_endpoint", "dao_ai_workshop_vs", "Vector Search endpoint")
dbutils.widgets.dropdown("reranker_model", "ms-marco-MiniLM-L-12-v2", ["ms-marco-MiniLM-L-12-v2", "ms-marco-TinyBERT-L-2-v2", "rank-T5-flan", "ms-marco-MultiBERT-L-12"], "Reranker (FlashRank)")

catalog: str = dbutils.widgets.get("catalog").strip()
if not catalog:
    raise ValueError("Set the catalog widget at the top of the notebook.")

params: dict[str, str] = {
    "username": username,
    "catalog": catalog,
    "schema": dbutils.widgets.get("schema").strip(),
    "llm_endpoint": dbutils.widgets.get("llm_endpoint").strip(),
    "decomposition_llm_endpoint": dbutils.widgets.get("decomposition_llm_endpoint").strip(),
    "embedding_model": dbutils.widgets.get("embedding_model").strip(),
    "vector_search_endpoint": dbutils.widgets.get("vector_search_endpoint").strip(),
    "reranker_model": dbutils.widgets.get("reranker_model").strip(),
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 -- Provision (products table, extend it, build vector index)
# MAGIC
# MAGIC The lab is self-contained: `data/products.sql` creates the base
# MAGIC products table (same DDL as Lab 2), then `data/products_extended.sql`
# MAGIC adds the `brand_name`, `price_tier`, `sku_prefix`, and `weight_lbs`
# MAGIC columns the instructed retriever uses as filter dimensions. Both
# MAGIC DDLs are idempotent.

# COMMAND ----------

from dao_ai.config import AppConfig

config: AppConfig = AppConfig.from_file("instructed_search.yaml", params=params)

for schema in config.schemas.values():
    schema.create()
    print(f"Schema ready: {schema.full_name}")

for dataset in config.datasets:
    dataset.create()
    print(f"Dataset applied: {dataset.table.full_name} <- {dataset.ddl}")

# COMMAND ----------

for vs in config.resources.vector_stores.values():
    vs.create()
    print(f"Vector index ready: {vs.index.full_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- The instructed retriever block
# MAGIC
# MAGIC The interesting part of `instructed_search.yaml` is the
# MAGIC `retrievers.<name>.instructed:` block. Three pieces:
# MAGIC
# MAGIC ```yaml
# MAGIC retrievers:
# MAGIC   instructed_retriever:
# MAGIC     vector_store: *products_vs
# MAGIC     search_parameters: { num_results: 50, query_type: HYBRID }
# MAGIC     instructed:
# MAGIC       columns: [...]               # schema metadata
# MAGIC       constraints: [...]           # natural-language hints
# MAGIC       decomposition:
# MAGIC         model: *decomposition_llm
# MAGIC         max_subqueries: 3
# MAGIC         examples: [...]            # few-shot exemplars
# MAGIC       rerank:
# MAGIC         model: *decomposition_llm
# MAGIC         instructions: "Prioritize..."  # natural-language reranker policy
# MAGIC         top_n: 10
# MAGIC     rerank:
# MAGIC       model: ${var.reranker_model}    # cross-encoder stage
# MAGIC       top_n: 20
# MAGIC ```
# MAGIC
# MAGIC Pipeline order:
# MAGIC 1. **Decomposition** -- haiku LLM splits *"Milwaukee tools under $100"* into `brand_name=MILWAUKEE`, `price<100`, and a residual semantic query.
# MAGIC 2. **Hybrid ANN search** -- 50 candidates per subquery, RRF-merged.
# MAGIC 3. **FlashRank rerank** -- cross-encoder promotes the most relevant 20.
# MAGIC 4. **Instruction-aware rerank** -- LLM applies natural-language priorities → top 10.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 -- Test locally

# COMMAND ----------

agent: CompiledStateGraph = config.as_graph()
print(f"Compiled app name: {config.app.name}")
try:
    config.display_graph()
except Exception as e:
    print(f"An exception has occurred: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Filter-heavy query with project intent

# COMMAND ----------

response: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "Show me Milwaukee power tools under $100 -- I'm comparing options for a kitchen refinishing project."}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Brand + price-tier query

# COMMAND ----------

response: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "What premium paint products do you carry from Benjamin Moore?"}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 -- Deploy as a Databricks App

# COMMAND ----------

from dao_ai.config import DeploymentTarget

config.deploy_agent(target=DeploymentTarget.APPS)
print(f"Deployed app: {config.app.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next
# MAGIC
# MAGIC [Lab 12 -- Genie Context-Aware Caching](../lab-12-genie-caching/) -- demonstrate the L1 (LRU) and L2 (similarity) caches over a Genie tool.
