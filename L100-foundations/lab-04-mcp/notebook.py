# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 4 -- Schema-wide Tool Discovery with MCP
# MAGIC
# MAGIC **Level:** L100
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Replace per-function tool declarations with a single `type: mcp` block referencing the schema.
# MAGIC - Add a serverless DBSQL MCP tool for ad-hoc queries that no UC function covers.
# MAGIC - Confirm the agent auto-discovers Lab 2's UC functions without re-declaring them.
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC An `mcp_assistant` that answers both a UC-function question (`"List 3 power tools"`) and an ad-hoc SQL question (`"What's the average price?"`) without any per-function YAML.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 - Install dependencies

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.64"
# MAGIC %restart_python

# COMMAND ----------

from importlib.metadata import version

print(f"dao-ai={version('dao-ai')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Auto-derive username
# MAGIC
# MAGIC The deployed app name is parameterized with `${var.username}` so
# MAGIC multiple students can deploy to the same workspace without name
# MAGIC collisions. We auto-derive it from your Databricks short name.

# COMMAND ----------

import re

from databricks.sdk import WorkspaceClient
from langgraph.graph.state import CompiledStateGraph
from typing import Any

w: WorkspaceClient = WorkspaceClient()
short_name: str = w.current_user.me().user_name.split("@")[0].lower()
username: str = re.sub(r"[^a-z0-9]+", "-", short_name).strip("-")[:13]
print(f"Derived username: {username}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 - Configure parameters

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (e.g. workshop_jane_doe)")
dbutils.widgets.text("schema", "dao_ai", "Schema")
dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-4-5", "LLM endpoint")

catalog: str = dbutils.widgets.get("catalog").strip()
if not catalog:
    raise ValueError("Set the catalog widget at the top of the notebook.")

params: dict[str, str] = {
    "username": username,
    "catalog": catalog,
    "schema": dbutils.widgets.get("schema").strip(),
    "llm_endpoint": dbutils.widgets.get("llm_endpoint").strip(),
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 - Build the config
# MAGIC
# MAGIC The big swap from lab 2: instead of declaring two
# MAGIC individual `unity_catalog` tools, we declare **one** `mcp` tool
# MAGIC and let it discover every UC function in the schema.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3a. Declare parameters and schema
# MAGIC
# MAGIC ```yaml
# MAGIC parameters:
# MAGIC   catalog:
# MAGIC     description: Unity Catalog catalog containing the workshop tables/functions.
# MAGIC   schema:
# MAGIC     description: Schema within the catalog for workshop assets.
# MAGIC     default: dao_ai
# MAGIC   llm_endpoint:
# MAGIC     description: Databricks LLM serving endpoint name.
# MAGIC     default: databricks-claude-sonnet-4-5
# MAGIC
# MAGIC schemas:
# MAGIC   workshop_schema: &workshop_schema
# MAGIC     catalog_name: ${var.catalog}
# MAGIC     schema_name: ${var.schema}
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3b. Declare the LLM
# MAGIC
# MAGIC ```yaml
# MAGIC resources:
# MAGIC   llms:
# MAGIC     default_llm: &default_llm
# MAGIC       name: ${var.llm_endpoint}
# MAGIC       temperature: 0.1
# MAGIC       max_tokens: 4096
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3c. Declare the MCP tools
# MAGIC
# MAGIC Two managed MCP servers, one YAML block each.
# MAGIC
# MAGIC - **`functions: <schema>`** -- exposes every UC function in the
# MAGIC   schema as a tool. Add a new UC function tomorrow and the agent
# MAGIC   picks it up on the next load.
# MAGIC - **`sql: true`** -- gives the agent a serverless DBSQL
# MAGIC   executor. Use sparingly: ad-hoc SQL is powerful but bypasses
# MAGIC   the typed-parameter audit trail of UC functions.
# MAGIC
# MAGIC ```yaml
# MAGIC tools:
# MAGIC   functions_mcp: &functions_mcp
# MAGIC     name: functions_mcp
# MAGIC     function:
# MAGIC       type: mcp
# MAGIC       functions: *workshop_schema
# MAGIC
# MAGIC   sql_mcp: &sql_mcp
# MAGIC     name: sql_mcp
# MAGIC     function:
# MAGIC       type: mcp
# MAGIC       sql: true
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3d. Declare the agent
# MAGIC
# MAGIC The prompt is the most important field on this chapter. The
# MAGIC agent has two overlapping tools (UC functions can answer many
# MAGIC of the same questions as raw SQL) -- the prompt's job is to
# MAGIC bias the model toward UC functions and away from SQL except
# MAGIC when needed. It also reminds the model to fully qualify table
# MAGIC names when it does write SQL.
# MAGIC
# MAGIC ```yaml
# MAGIC agents:
# MAGIC   mcp_agent: &mcp_agent
# MAGIC     name: mcp_agent
# MAGIC     description: Agent backed by managed MCP servers for UC functions and SQL.
# MAGIC     model: *default_llm
# MAGIC     tools:
# MAGIC       - *functions_mcp
# MAGIC       - *sql_mcp
# MAGIC     prompt: |
# MAGIC       You have access to Unity Catalog functions and a SQL execution
# MAGIC       tool through MCP. Prefer UC functions when available (they have
# MAGIC       typed parameters and audit trails). Use SQL for ad-hoc queries
# MAGIC       that UC functions don't cover. Always qualify tables as
# MAGIC       catalog.schema.table_name.
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3e. Declare the app
# MAGIC
# MAGIC ```yaml
# MAGIC app:
# MAGIC   name: dao_ws_04_mcp
# MAGIC   deployment_target: apps
# MAGIC   agents:
# MAGIC     - *mcp_agent
# MAGIC   orchestration:
# MAGIC     swarm:
# MAGIC       default_agent: *mcp_agent
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3f. Load and compile

# COMMAND ----------

from dao_ai.config import AppConfig

config: AppConfig = AppConfig.from_file("mcp_assistant.yaml", params=params)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 - Provision schema, products table, and UC functions
# MAGIC
# MAGIC The MCP `functions:` tool discovers every UC function in the
# MAGIC schema at agent-build time, so the functions need to exist
# MAGIC **before** we call `as_graph()`. This lab provisions its own
# MAGIC products table and two UC functions so it's self-contained.

# COMMAND ----------

for schema in config.schemas.values():
    schema.create()
    print(f"Schema ready:   {schema.full_name}")

for dataset in config.datasets:
    dataset.create()
    print(f"Table loaded:   {dataset.table.full_name}")

for uc_fn in config.unity_catalog_functions:
    uc_fn.create()
    print(f"Function ready: {uc_fn.function.full_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 - Test locally

# COMMAND ----------

agent: CompiledStateGraph = config.as_graph()
try:
    config.display_graph()
except Exception as e:
    print(f"An exception has occurred: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Question that should hit a UC function

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

response: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "List 3 power tools from our catalog."}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Question that requires ad-hoc SQL (no pre-built function)

# COMMAND ----------

response: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "What's the average price across all products?"}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 - Deploy as a Databricks App

# COMMAND ----------

from dao_ai.config import DeploymentTarget

config.deploy_agent(target=DeploymentTarget.APPS)
print(f"Deployed app: {config.app.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next
# MAGIC
# MAGIC [Lab 5: REST](../../L200-real-agents/lab-05-rest/) - call an external HTTP API.
