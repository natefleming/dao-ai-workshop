# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 6 -- Knowledge-base Retrieval with Vector Search
# MAGIC
# MAGIC **Level:** L200
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Declare a `vector_stores:` resource with Delta Sync over a KB articles table.
# MAGIC - Configure a `retrievers:` block with ANN search parameters.
# MAGIC - Layer a FlashRank cross-encoder reranker on top of ANN for precision (50 candidates → top 5).
# MAGIC - Compare retrieval quality across three steps: ungrounded baseline → ANN → ANN+rerank.
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC A `kb-search` agent that answers `"How do I rotate my API keys without downtime?"` by retrieving and citing the matching KB article.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 -- Install dependencies

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.64" databricks-vectorsearch
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
    "embedding_model": dbutils.widgets.get("embedding_model").strip(),
    "vector_search_endpoint": dbutils.widgets.get("vector_search_endpoint").strip(),
    "reranker_model": dbutils.widgets.get("reranker_model").strip(),
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 -- Provision shared resources
# MAGIC
# MAGIC Use the **final** config to create the schema, seed kb_articles,
# MAGIC enable Change Data Feed, and build the vector index. **First-run
# MAGIC provisioning takes 5-10 minutes** as the index builds.

# COMMAND ----------

from dao_ai.config import AppConfig

final_config: AppConfig = AppConfig.from_file("03_kb_assistant_with_reranking.yaml", params=params)

for schema in final_config.schemas.values():
    schema.create()
    print(f"Schema ready: {schema.full_name}")

for dataset in final_config.datasets:
    dataset.create()
    print(f"Table loaded: {dataset.table.full_name}")

# COMMAND ----------

# Vector Search needs the source table's Change Data Feed enabled so the
# index can sync incrementally. `data/kb_articles.sql` declares
# `TBLPROPERTIES (delta.enableChangeDataFeed = true)` on CREATE TABLE,
# so the property is already set by the dataset.create() above.

# COMMAND ----------

for vs in final_config.resources.vector_stores.values():
    vs.create()
    print(f"Vector index ready: {vs.index.full_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- Walk the steps

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4a. `01_kb_assistant.yaml` -- ungrounded baseline
# MAGIC
# MAGIC No retrieval. The agent has only its prompt knowledge -- watch
# MAGIC how it responds when a customer asks a specific KB question.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Enable MLflow autolog
# MAGIC
# MAGIC `mlflow.langchain.autolog()` registers tracers on every LangChain
# MAGIC call so the agent's tool calls, LLM completions, and graph
# MAGIC transitions land in the active MLflow experiment as traces.
# MAGIC Open the Experiment from the right-hand panel after running an
# MAGIC inference cell below to inspect what the agent did.

# COMMAND ----------

import mlflow

mlflow.langchain.autolog()

# COMMAND ----------

config: AppConfig = AppConfig.from_file("01_kb_assistant.yaml", params=params)
agent: CompiledStateGraph = config.as_graph()

response: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "How do I rotate my API keys without downtime?"}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4b. `02_kb_assistant_with_search.yaml` -- adds ANN retrieval

# COMMAND ----------

config: AppConfig = AppConfig.from_file("02_kb_assistant_with_search.yaml", params=params)
agent: CompiledStateGraph = config.as_graph()

response: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "How do I rotate my API keys without downtime?"}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4c. `03_kb_assistant_with_reranking.yaml` -- adds reranking (final)
# MAGIC
# MAGIC ANN provides recall (50 candidates), FlashRank provides
# MAGIC precision (top 5 reranked).

# COMMAND ----------

config: AppConfig = AppConfig.from_file("03_kb_assistant_with_reranking.yaml", params=params)
agent: CompiledStateGraph = config.as_graph()

try:
    config.display_graph()
except Exception as e:
    print(f"An exception has occurred: {e}")

# COMMAND ----------

response: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "How do I rotate my API keys without downtime?"}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 -- Deploy as a Databricks App

# COMMAND ----------

from dao_ai.config import DeploymentTarget

config.deploy_agent(target=DeploymentTarget.APPS)
print(f"Deployed app: {config.app.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next
# MAGIC
# MAGIC [Lab 7](../lab-07-memory/) -- give the support agent persistent
# MAGIC memory so returning customers don't have to repeat themselves.
