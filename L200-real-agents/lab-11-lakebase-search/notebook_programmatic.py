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

# MAGIC %pip install "dao-ai>=0.1.106"
# MAGIC %restart_python

# COMMAND ----------

import re
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
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

retriever = LakebaseRetrieverModel(
    vector_store=LakebaseVectorStoreModel(
        database=DatabaseModel(
            project=lakebase_project,
            client_id=SecretVariableModel(scope=sp_secret_scope, secret="DAO_AI_SP_CLIENT_ID"),
            client_secret=SecretVariableModel(scope=sp_secret_scope, secret="DAO_AI_SP_CLIENT_SECRET"),
        ),
        table="kb_articles",
        content_column="passage",
        embedding_column="embedding",
        tsvector_column="passage_tsv",
        embedding_model="databricks-gte-large-en",
        metadata_columns=["category", "priority"],
    ),
    search_parameters=SearchParametersModel(query_type="HYBRID", num_results=20),
    rerank=RerankParametersModel(model="ms-marco-MiniLM-L-12-v2", top_n=5),
)

tool = ToolModel(name="kb_search", function=LakebaseSearchToolModel(retriever=retriever))
agent = AgentModel(
    name="kb_assistant",
    model=InferenceEndpointModel(name="databricks-claude-sonnet-4-5", temperature=0.1, max_tokens=4096),
    tools=[tool],
    prompt="You are a knowledge-base assistant. Always call `kb_search` before answering. Cite [d##] after each fact.",
)

config = AppConfig(
    retrievers={"kb_retriever": retriever},
    tools={"kb_search": tool},
    agents={"kb_assistant": agent},
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Provision
# MAGIC
# MAGIC Assumes `notebook.py` has already been run once to seed the rows.

# COMMAND ----------

retriever.vector_store.provision(
    dimension=1024,
    metadata_column_types={"priority": "int"},
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Retrieve

# COMMAND ----------

import json

kb_tool = tool.function.as_tools()[0]
docs = json.loads(kb_tool.invoke({"query": "How do I reset my password?"}))
for d in docs:
    print(f"[{d['metadata']['id']}] priority={d['metadata']['priority']} :: {d['page_content']}")
