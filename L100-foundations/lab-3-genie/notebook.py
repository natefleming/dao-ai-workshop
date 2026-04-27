# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 3 -- NL Analytics with Genie
# MAGIC
# MAGIC **Level:** L100
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Add a `genie_rooms:` resource pointing at a Databricks Genie Space.
# MAGIC - Wrap the room as a `factory` tool via `dao_ai.tools.create_genie_tool`.
# MAGIC - See the agent delegate open-ended analytical questions to Genie instead of needing a hand-written UC function.
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC An `analyst` agent that answers `"How many products do we have per category?"` by calling Genie and summarising the result.

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
# MAGIC
# MAGIC `analyst.yaml` declares parameters in a top-level `parameters:`
# MAGIC block. We override them at load time via the `params={...}`
# MAGIC kwarg of `AppConfig.from_file`. Defaults declared in YAML kick
# MAGIC in for any parameter we don't pass.

# COMMAND ----------

dbutils.widgets.text("genie_space_id", "", "Genie Space ID")
dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-4-5", "LLM endpoint")

genie_space_id: str = dbutils.widgets.get("genie_space_id").strip()
if not genie_space_id:
    raise ValueError("Set the genie_space_id widget at the top of the notebook.")

params: dict[str, str] = {
    "username": username,
    "genie_space_id": genie_space_id,
    "llm_endpoint": dbutils.widgets.get("llm_endpoint").strip(),
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 - Build the config
# MAGIC
# MAGIC The new pieces in this chapter are the **`genie_rooms` resource**
# MAGIC (a reference to your Genie Space) and the **factory tool** that
# MAGIC wraps it as a callable.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3a. Declare parameters
# MAGIC
# MAGIC `genie_space_id` is required -- we have to know which space to
# MAGIC talk to.
# MAGIC
# MAGIC ```yaml
# MAGIC parameters:
# MAGIC   genie_space_id:
# MAGIC     description: Databricks Genie Space ID. Copy from the Genie URL.
# MAGIC   llm_endpoint:
# MAGIC     description: Databricks LLM serving endpoint name.
# MAGIC     default: databricks-claude-sonnet-4-5
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3b. Declare the LLM and the Genie room
# MAGIC
# MAGIC `genie_rooms:` lives under `resources:` alongside `llms:`. Each
# MAGIC entry points at one Genie Space by id. The agent does not need
# MAGIC the URL, schema, or table list -- Genie already knows those from
# MAGIC its own configuration.
# MAGIC
# MAGIC ```yaml
# MAGIC resources:
# MAGIC   llms:
# MAGIC     default_llm: &default_llm
# MAGIC       name: ${var.llm_endpoint}
# MAGIC       temperature: 0.1
# MAGIC       max_tokens: 4096
# MAGIC
# MAGIC   genie_rooms:
# MAGIC     workshop_genie: &workshop_genie
# MAGIC       name: "Workshop Genie Room"
# MAGIC       description: "Genie space over the workshop products table"
# MAGIC       space_id: ${var.genie_space_id}
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3c. Wrap the Genie room as a tool
# MAGIC
# MAGIC Unlike chapter 2's `type: unity_catalog` tools, Genie tools are
# MAGIC `type: factory` -- dao-ai calls a Python factory function at
# MAGIC build time, passes the `args:`, and gets back a tool. The
# MAGIC `description:` here is what the LLM sees when it decides
# MAGIC whether to use the tool.
# MAGIC
# MAGIC ```yaml
# MAGIC tools:
# MAGIC   genie_tool: &genie_tool
# MAGIC     name: ask_genie
# MAGIC     function:
# MAGIC       type: factory
# MAGIC       name: dao_ai.tools.create_genie_tool
# MAGIC       args:
# MAGIC         name: ask_genie
# MAGIC         description: >
# MAGIC           Ask a Genie Space a natural-language question about products,
# MAGIC           inventory, or sales.
# MAGIC         genie_room: *workshop_genie
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3d. Declare the analyst agent
# MAGIC
# MAGIC The agent's prompt is short on purpose: Genie does the SQL
# MAGIC reasoning, the agent's job is only to forward questions and
# MAGIC summarize results.
# MAGIC
# MAGIC ```yaml
# MAGIC agents:
# MAGIC   analyst: &analyst
# MAGIC     name: analyst
# MAGIC     description: A data analyst agent backed by a Genie Space.
# MAGIC     model: *default_llm
# MAGIC     tools:
# MAGIC       - *genie_tool
# MAGIC     prompt: |
# MAGIC       You are a data analyst. For any question about products,
# MAGIC       inventory, or sales, call the ask_genie tool and summarize
# MAGIC       the result in plain language. Do not make up numbers.
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3e. Declare the app
# MAGIC
# MAGIC ```yaml
# MAGIC app:
# MAGIC   name: dao_ws_03_genie
# MAGIC   deployment_target: apps
# MAGIC   agents:
# MAGIC     - *analyst
# MAGIC   orchestration:
# MAGIC     swarm:
# MAGIC       default_agent: *analyst
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3f. Load and compile

# COMMAND ----------

from dao_ai.config import AppConfig

config: AppConfig = AppConfig.from_file("analyst.yaml", params=params)
agent: CompiledStateGraph = config.as_graph()

try:
    config.display_graph()
except Exception as e:
    print(f"An exception has occurred: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 - Test locally
# MAGIC
# MAGIC Ask a question that requires Genie to generate SQL. The agent
# MAGIC should call `ask_genie`, receive a result table, and summarize.

# COMMAND ----------

response: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "How many products do we have per category?"}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 - Deploy as a Databricks App
# MAGIC
# MAGIC Generate `databricks.yaml` from `analyst.yaml` and deploy via
# MAGIC Asset Bundles. Set the `GENIE_SPACE_ID` environment variable
# MAGIC on the deployed app -- dao-ai's env-var fallback maps it to
# MAGIC the `genie_space_id` parameter automatically.

# COMMAND ----------

from dao_ai.config import DeploymentTarget

config.deploy_agent(target=DeploymentTarget.APPS)
print(f"Deployed app: {config.app.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next
# MAGIC
# MAGIC [Chapter 4: MCP](../lab-4-mcp/) - instead of declaring each UC
# MAGIC function as its own tool, let the agent discover a whole
# MAGIC schema's worth of functions via a managed MCP server.
