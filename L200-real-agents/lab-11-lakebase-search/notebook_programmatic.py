# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 11 -- Programmatic Config for the Lakebase Agent
# MAGIC
# MAGIC **Level:** L200 (bonus)
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Rebuild the **exact same** `kb_assistant` from `03_reranked.yaml` -- Lakebase HYBRID + FlashRank rerank -- in pure Python, no YAML file involved.
# MAGIC - Prove the mapping YAML <-> Python is 1:1: same models, same fields, same result from `agent.apredict(...)`.
# MAGIC - Show the pattern you'd reach for when generating retriever configs dynamically (one per tenant, one per Lakebase project, sweep across `rerank` on/off) or embedding dao-ai inside a larger Python service.
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC The same `kb_assistant` agent as the main notebook, invoked identically, but built end-to-end from Python.
# MAGIC
# MAGIC > This lab is a **domain-specific** view (lakebase_search + HYBRID + FlashRank) of programmatic construction. For the general treatment -- provisioning schemas, UC functions, datasets, and full app deployment from Python -- see [Lab 13 (L300)](../../L300-advanced/lab-13-programmatic/).

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 -- Install dependencies

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.105"
# MAGIC %restart_python

# COMMAND ----------

from importlib.metadata import version

print(f"dao-ai={version('dao-ai')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 -- Configure parameters
# MAGIC
# MAGIC Same widgets as `notebook.py`. In this variant they populate Python variables directly instead of getting substituted into a YAML template.

# COMMAND ----------

import re
from typing import Any

from databricks.sdk import WorkspaceClient

w: WorkspaceClient = WorkspaceClient()
short_name: str = w.current_user.me().user_name.split("@")[0].lower()
username: str = re.sub(r"[^a-z0-9]+", "-", short_name).strip("-")[:13]
print(f"Derived username: {username}")

dbutils.widgets.text("lakebase_project", "", "Lakebase project name")
dbutils.widgets.text("secret_scope", "", "Secret scope (holds SP creds)")
dbutils.widgets.text("schema_name", "public", "Postgres schema")
dbutils.widgets.text("table_name", "kb_articles", "Postgres table")
dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-4-5", "LLM endpoint")
dbutils.widgets.text("embedding_model", "databricks-gte-large-en", "Embedding endpoint")

lakebase_project: str = dbutils.widgets.get("lakebase_project").strip()
secret_scope: str = dbutils.widgets.get("secret_scope").strip()
if not lakebase_project or not secret_scope:
    raise ValueError(
        "Set the `lakebase_project` and `secret_scope` widgets at the top of the notebook."
    )
schema_name: str = dbutils.widgets.get("schema_name").strip()
table_name: str = dbutils.widgets.get("table_name").strip()
llm_endpoint: str = dbutils.widgets.get("llm_endpoint").strip()
embedding_model: str = dbutils.widgets.get("embedding_model").strip()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 -- Build the config in Python
# MAGIC
# MAGIC Each block below is the Python equivalent of the matching YAML block in `03_reranked.yaml`. Compare side by side:
# MAGIC
# MAGIC | `03_reranked.yaml` block | Python equivalent below |
# MAGIC |---|---|
# MAGIC | `variables.client_id` (options list) | `SecretVariableModel(scope=..., secret=...)` |
# MAGIC | `resources.databases.kb_lakebase` | `DatabaseModel(project=..., client_id=..., ...)` |
# MAGIC | `resources.models.default_llm` | `InferenceEndpointModel(name=..., temperature=..., max_tokens=...)` |
# MAGIC | `retrievers.kb_retriever` | `LakebaseRetrieverModel(vector_store=..., search_parameters=..., rerank=...)` |
# MAGIC | `retrievers.*.vector_store` | `LakebaseVectorStoreModel(database=..., table=..., embedding_column=..., ...)` |
# MAGIC | `retrievers.*.search_parameters` | `SearchParametersModel(query_type=..., num_results=...)` |
# MAGIC | `retrievers.*.rerank` | `RerankParametersModel(model=..., top_n=...)` |
# MAGIC | `tools.kb_search.function` | `LakebaseSearchToolModel(retriever=...)` |
# MAGIC | `tools.kb_search` | `ToolModel(name=..., function=LakebaseSearchToolModel(...))` |
# MAGIC | `agents.kb_assistant` | `AgentModel(name=..., model=..., tools=[...], prompt=...)` |
# MAGIC | top-level `app`/`retrievers`/`tools`/`agents` | `AppConfig(retrievers={...}, tools={...}, agents={...})` |

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

# ---- variables ----------------------------------------------------
# YAML: variables.client_id.options[0]: { scope: ${var.secret_scope}, secret: SP_CLIENT_ID }
client_id = SecretVariableModel(scope=secret_scope, secret="SP_CLIENT_ID")
client_secret = SecretVariableModel(scope=secret_scope, secret="SP_CLIENT_SECRET")
workspace_host = SecretVariableModel(scope=secret_scope, secret="DATABRICKS_HOST")

# ---- resources.databases.kb_lakebase ------------------------------
kb_lakebase = DatabaseModel(
    project=lakebase_project,
    client_id=client_id,
    client_secret=client_secret,
    workspace_host=workspace_host,
)

# ---- resources.models.default_llm ---------------------------------
default_llm = InferenceEndpointModel(
    name=llm_endpoint,
    temperature=0.1,
    max_tokens=4096,
)

# ---- retrievers.kb_retriever --------------------------------------
kb_retriever = LakebaseRetrieverModel(
    vector_store=LakebaseVectorStoreModel(
        database=kb_lakebase,
        schema_name=schema_name,
        table=table_name,
        content_column="passage",
        embedding_column="embedding",
        tsvector_column="passage_tsv",         # required for HYBRID
        embedding_model=embedding_model,
        metadata_columns=["category", "priority"],
    ),
    search_parameters=SearchParametersModel(
        query_type="HYBRID",
        num_results=20,                          # wider net for the reranker
    ),
    rerank=RerankParametersModel(
        model="ms-marco-MiniLM-L-12-v2",
        top_n=5,
    ),
)

# ---- tools.kb_search ----------------------------------------------
kb_search_tool = ToolModel(
    name="kb_search",
    function=LakebaseSearchToolModel(retriever=kb_retriever),
)

# ---- agents.kb_assistant ------------------------------------------
kb_assistant = AgentModel(
    name="kb_assistant",
    model=default_llm,
    tools=[kb_search_tool],
    prompt=(
        "You are a knowledge-base assistant. Always call `kb_search` before "
        "answering. Cite the article id in square brackets after each fact, "
        "e.g. [d01]."
    ),
)

# ---- top-level config ---------------------------------------------
config = AppConfig(
    retrievers={"kb_retriever": kb_retriever},
    tools={"kb_search": kb_search_tool},
    agents={"kb_assistant": kb_assistant},
)

print("Python-built AppConfig:")
print(f"  retrievers: {list(config.retrievers.keys())}")
print(f"  tools:      {list(config.tools.keys())}")
print(f"  agents:     {list(config.agents.keys())}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- Invoke the agent
# MAGIC
# MAGIC Same `initialize()` -> `as_responses_agent()` -> `apredict()` shape as the YAML-driven notebook. The only difference is where the `AppConfig` came from.

# COMMAND ----------

import asyncio
import nest_asyncio

nest_asyncio.apply()

from mlflow.types.responses import ResponsesAgentRequest

config.initialize()
agent = config.as_responses_agent()


async def ask(question: str) -> str:
    resp = await agent.apredict(
        ResponsesAgentRequest(input=[{"role": "user", "content": question}])
    )
    for item in resp.output:
        if getattr(item, "type", None) == "message":
            for content in item.content:
                if content.get("type") in {"output_text", "text"}:
                    return content.get("text") or content.get("value") or ""
    return "<no text response>"


for q in ["How do I reset my password?", "When do password reset links expire?"]:
    print(f"\nQ: {q}")
    print(f"A: {asyncio.run(ask(q))}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 -- Prove YAML <-> Python parity
# MAGIC
# MAGIC Load `03_reranked.yaml` and compare the resulting Pydantic tree to the one we just built.

# COMMAND ----------

yaml_cfg = AppConfig.from_file(
    "03_reranked.yaml",
    params={
        "username": username,
        "lakebase_project": lakebase_project,
        "secret_scope": secret_scope,
        "schema_name": schema_name,
        "table_name": table_name,
        "llm_endpoint": llm_endpoint,
        "embedding_model": embedding_model,
        "reranker_model": "ms-marco-MiniLM-L-12-v2",
    },
)

# The two configs won't be byte-for-byte identical (YAML carries the
# top-level `app:` block; the Python variant above omits it since we're
# only running locally in this cell). But the retriever + tool + agent
# trees -- the pieces that actually drive retrieval -- should match.
py_retriever = config.retrievers["kb_retriever"].model_dump(exclude_none=True)
yaml_retriever = yaml_cfg.retrievers["kb_retriever"].model_dump(exclude_none=True)
print("retrievers match:", py_retriever == yaml_retriever)

py_tool = config.tools["kb_search"].model_dump(exclude_none=True)
yaml_tool = yaml_cfg.tools["kb_search"].model_dump(exclude_none=True)
print("tools match:     ", py_tool == yaml_tool)

# COMMAND ----------

# MAGIC %md
# MAGIC ## When to use Python vs YAML
# MAGIC
# MAGIC - **YAML wins** when the config is mostly static, you want config-as-code review, or non-developers will edit it. All L100/L200 labs use YAML.
# MAGIC - **Python wins** when you generate configs dynamically -- one retriever per tenant from a database query, sweeping `rerank` on/off for A/B tests, or embedding dao-ai inside a larger Python service.
# MAGIC - **Mixing is fine.** Load a YAML with `AppConfig.from_file(...)`, then mutate fields on the returned object before `initialize()` / `as_responses_agent()`.
# MAGIC
# MAGIC ## Next
# MAGIC
# MAGIC - `notebook.py` in this same lab -- the YAML-driven version of exactly this agent.
# MAGIC - [Lab 13 (L300)](../../L300-advanced/lab-13-programmatic/) -- the general treatment: provisions schemas, UC functions, datasets, and full app deployment from Python.
