# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 11 -- Lakebase Search Retrieval
# MAGIC
# MAGIC **Level:** L200
# MAGIC
# MAGIC Build a knowledge-base assistant that retrieves from **Lakebase Postgres**
# MAGIC using hybrid dense + BM25 search with FlashRank reranking. Same tool
# MAGIC schema as `ai_search`; different backend.

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.107"
# MAGIC %restart_python

# COMMAND ----------

import re
from databricks.sdk import WorkspaceClient

w: WorkspaceClient = WorkspaceClient()
short_name: str = w.current_user.me().user_name.split("@")[0].lower()
username: str = re.sub(r"[^a-z0-9]+", "-", short_name).strip("-")[:13]

dbutils.widgets.text("lakebase_project", "retail-consumer-goods", "Lakebase project")
dbutils.widgets.text("sp_secret_scope", "dao_ai_workshop", "SP secret scope")

params: dict[str, str] = {
    "username": username,
    "lakebase_project": dbutils.widgets.get("lakebase_project").strip(),
    "sp_secret_scope": dbutils.widgets.get("sp_secret_scope").strip(),
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load the config

# COMMAND ----------

from dao_ai.config import (
    AppConfig,
    DatabaseModel,
    LakebaseRetrieverModel,
    LakebaseVectorStoreModel,
)

config: AppConfig = AppConfig.from_file("kb_assistant.yaml", params=params)
retriever: LakebaseRetrieverModel = config.retrievers["kb_retriever"]
vector_store: LakebaseVectorStoreModel = retriever.vector_store
database: DatabaseModel = vector_store.database

# COMMAND ----------

# MAGIC %md
# MAGIC ## Provision the Lakebase table
# MAGIC
# MAGIC `provision()` idempotently creates the extensions (`lakebase_vector`,
# MAGIC `lakebase_text`), the `kb_articles` table, and the ANN + BM25 indexes.
# MAGIC Safe to re-run.

# COMMAND ----------

vector_store.provision(
    dimension=1024,  # databricks-gte-large-en output dimension
    metadata_column_types={"priority": "int"},
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Seed the KB rows

# COMMAND ----------

from pathlib import Path

seed_sql: str = Path("data/kb_articles.sql").read_text()
database.execute_update(seed_sql)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Backfill embeddings
# MAGIC
# MAGIC The seed rows have `embedding=NULL` so the DDL stays portable across
# MAGIC embedding models. Encode each passage now.

# COMMAND ----------

from dao_ai.lakebase import backfill_embeddings

n_backfilled: int = backfill_embeddings(vector_store)
print(f"backfilled {n_backfilled} embeddings")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Retrieve

# COMMAND ----------

import json

tool = config.tools["kb_search"].function.as_tools()[0]
docs: list[dict] = json.loads(tool.invoke({"query": "How do I reset my password?"}))
for doc in docs:
    meta: dict = doc["metadata"]
    print(f"[{meta['id']}] priority={meta['priority']} :: {doc['page_content']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Run inference against the agent
# MAGIC
# MAGIC `config.as_graph()` compiles the retriever + tool + agent into a
# MAGIC LangGraph. The agent decides when to call `kb_search` and answers
# MAGIC with citations.

# COMMAND ----------

from typing import Any

import mlflow
from langgraph.graph.state import CompiledStateGraph

mlflow.langchain.autolog()

agent: CompiledStateGraph = config.as_graph()

response: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "How do I reset my password?"}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Deploy as a Databricks App

# COMMAND ----------

from dao_ai.config import DeploymentTarget

config.deploy_agent(target=DeploymentTarget.APPS)
print(f"Deployed app: {config.app.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cleanup (optional)

# COMMAND ----------

# database.execute_update("DROP TABLE IF EXISTS kb_articles;")
