# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 11 -- Programmatic Config
# MAGIC
# MAGIC **Level:** L200 (bonus)
# MAGIC
# MAGIC Same agent as `notebook.py` -- built entirely from Python instead of
# MAGIC YAML. Useful when you generate configs dynamically (per tenant, per
# MAGIC dataset) or embed dao-ai inside a larger Python service.

# COMMAND ----------

# MAGIC %uv pip install "dao-ai[rerank]==0.2.4"
# MAGIC %restart_python

# COMMAND ----------

import nest_asyncio
nest_asyncio.apply()

# COMMAND ----------

import re

from databricks.sdk import WorkspaceClient

w: WorkspaceClient = WorkspaceClient()
short_name: str = w.current_user.me().user_name.split("@")[0].lower()
username: str = re.sub(r"[^a-z0-9]+", "-", short_name).strip("-")[:13]

dbutils.widgets.text("lakebase_project", "retail-consumer-goods", "Lakebase project")
dbutils.widgets.text("sp_secret_scope", "dao_ai_workshop", "SP secret scope")

lakebase_project: str = dbutils.widgets.get("lakebase_project").strip()
sp_secret_scope: str = dbutils.widgets.get("sp_secret_scope").strip()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Build the config in Python

# COMMAND ----------

from dao_ai.config import (
    AgentModel,
    AppConfig,
    AppModel,
    DatabaseModel,
    InferenceEndpointModel,
    LakebaseRetrieverModel,
    LakebaseSearchToolModel,
    LakebaseVectorStoreModel,
    RerankParametersModel,
    SearchParametersModel,
    SecretVariableModel,
    ToolModel,
)

database: DatabaseModel = DatabaseModel(
    project=lakebase_project,
    client_id=SecretVariableModel(scope=sp_secret_scope, secret="DAO_AI_SP_CLIENT_ID"),
    client_secret=SecretVariableModel(scope=sp_secret_scope, secret="DAO_AI_SP_CLIENT_SECRET"),
)

vector_store: LakebaseVectorStoreModel = LakebaseVectorStoreModel(
    database=database,
    table="kb_articles",
    content_column="passage",
    embedding_column="embedding",
    tsvector_column="passage_tsv",
    embedding_model="databricks-gte-large-en",
    metadata_columns=["category", "priority"],
)

retriever: LakebaseRetrieverModel = LakebaseRetrieverModel(
    vector_store=vector_store,
    search_parameters=SearchParametersModel(query_type="HYBRID", num_results=20),
    rerank=RerankParametersModel(model="ms-marco-MiniLM-L-12-v2", top_n=5),
)

tool: ToolModel = ToolModel(
    name="kb_search",
    function=LakebaseSearchToolModel(retriever=retriever),
)

agent: AgentModel = AgentModel(
    name="kb_assistant",
    model=InferenceEndpointModel(name="databricks-claude-sonnet-4-5", temperature=0.1, max_tokens=4096),
    tools=[tool],
    prompt="You are a knowledge-base assistant. Always call `kb_search` before answering. Cite [d##] after each fact.",
)

config: AppConfig = AppConfig(
    retrievers={"kb_retriever": retriever},
    tools={"kb_search": tool},
    agents={"kb_assistant": agent},
    # Databricks Apps deploys don't need an MLflow registered model
    # (Model Serving deploys do). The deploy target is passed at deploy
    # time via `deploy_agent(mode=ServingMode.APPS)`, not on the config.
    app=AppModel(
        name=f"kb-assistant-{username}",
        agents=[agent],
    ),
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Provision the Lakebase table

# COMMAND ----------

vector_store.provision(
    dimension=1024,
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

# COMMAND ----------

from dao_ai.lakebase import backfill_embeddings

n_backfilled: int = backfill_embeddings(vector_store)
print(f"backfilled {n_backfilled} embeddings")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Retrieve

# COMMAND ----------

import json

from langchain_core.tools import StructuredTool

[tool_model] = config.find_tools(lambda t: t.name == "kb_search")
kb_tool: StructuredTool = tool_model.function.as_tools()[0]
docs: list[dict] = json.loads(kb_tool.invoke({"query": "How do I reset my password?"}))
for doc in docs:
    meta: dict = doc["metadata"]
    print(f"[{meta['id']}] priority={meta['priority']} :: {doc['page_content']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Run inference against the agent

# COMMAND ----------

from typing import Any

import mlflow
from langgraph.graph.state import CompiledStateGraph

mlflow.langchain.autolog()

graph: CompiledStateGraph = config.as_graph()

response: dict[str, Any] = await graph.ainvoke(
    {"messages": [{"role": "user", "content": "How do I reset my password?"}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Deploy as a Databricks App

# COMMAND ----------

from dao_ai.config import ServingMode

config.deploy_agent(mode=ServingMode.APPS)
print(f"Deployed app: {config.app.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cleanup (optional)

# COMMAND ----------

# database.execute_update("DROP TABLE IF EXISTS kb_articles;")
