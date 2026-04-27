# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 1 -- Your First dao-ai Agent
# MAGIC
# MAGIC **Level:** L100
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Read a 30-line `dao_ai.yaml` and understand each top-level section.
# MAGIC - Auto-derive a per-student `username` and inject it via `params={...}`.
# MAGIC - Compile the YAML to a runnable agent with `AppConfig.from_file(...).as_graph()`.
# MAGIC - Deploy as a Databricks App with one call: `config.deploy_agent(target=DeploymentTarget.APPS)`.
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC A live `greeter-hw-<your-username>` Databricks App that responds to `"Hi! Is this thing on?"`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 -- Install dependencies

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.60"
# MAGIC %restart_python

# COMMAND ----------

from importlib.metadata import version

print(f"dao-ai={version('dao-ai')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 -- Configure parameters
# MAGIC
# MAGIC `greeter.yaml` declares parameters in a top-level `parameters:`
# MAGIC block. We override them at load time via the `params={...}`
# MAGIC kwarg of `AppConfig.from_file`. Defaults declared in YAML kick
# MAGIC in for any parameter we don't pass.
# MAGIC
# MAGIC `username` is auto-derived from your Databricks short name so
# MAGIC multiple students can deploy to the same workspace without
# MAGIC app-name collisions.

# COMMAND ----------

import re

from databricks.sdk import WorkspaceClient
from langgraph.graph.state import CompiledStateGraph
from typing import Any

w: WorkspaceClient = WorkspaceClient()
short_name: str = w.current_user.me().user_name.split("@")[0].lower()
username: str = re.sub(r"[^a-z0-9]+", "-", short_name).strip("-")[:13]
print(f"Derived username: {username}")

dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-4-5", "LLM endpoint")

params: dict[str, str] = {
    "username": username,
    "llm_endpoint": dbutils.widgets.get("llm_endpoint").strip(),
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 -- Build the config
# MAGIC
# MAGIC `greeter.yaml` is the **declarative description of your agent**.
# MAGIC We'll walk through it section by section.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3a. Declare parameters
# MAGIC
# MAGIC Every `${var.NAME}` reference elsewhere in the file must be
# MAGIC declared here. Parameters with no `default:` are **required**.
# MAGIC `username` is required (the notebook supplies it). `llm_endpoint`
# MAGIC has a default.
# MAGIC
# MAGIC ```yaml
# MAGIC parameters:
# MAGIC   username:
# MAGIC     description: Per-student username for unique deployment names. Auto-set by the notebook.
# MAGIC   llm_endpoint:
# MAGIC     description: Databricks LLM serving endpoint name.
# MAGIC     default: databricks-claude-sonnet-4-5
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3b. Declare the LLM resource
# MAGIC
# MAGIC `resources:` is the registry of physical things the agent uses --
# MAGIC LLMs, schemas, databases, vector stores, Genie rooms. Anchors
# MAGIC (`&default_llm`) let us reference the same resource elsewhere.
# MAGIC
# MAGIC ```yaml
# MAGIC resources:
# MAGIC   llms:
# MAGIC     default_llm: &default_llm
# MAGIC       name: ${var.llm_endpoint}
# MAGIC       temperature: 0.1
# MAGIC       max_tokens: 2048
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3c. Declare the agent
# MAGIC
# MAGIC An `agent` ties together a model, optional tools, and a system
# MAGIC prompt. Chapter 1 has no tools.
# MAGIC
# MAGIC ```yaml
# MAGIC agents:
# MAGIC   greeter: &greeter
# MAGIC     name: greeter
# MAGIC     model: *default_llm
# MAGIC     prompt: |
# MAGIC       You are the welcome agent for the dao-ai workshop...
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3d. Declare the app
# MAGIC
# MAGIC `app:` is what gets deployed. The `name` uses `${var.username}`
# MAGIC so each student's deployment is unique.
# MAGIC
# MAGIC ```yaml
# MAGIC app:
# MAGIC   name: greeter-hw-${var.username}
# MAGIC   deployment_target: apps
# MAGIC   agents: [*greeter]
# MAGIC   orchestration:
# MAGIC     swarm:
# MAGIC       default_agent: *greeter
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3e. Load and compile
# MAGIC
# MAGIC `AppConfig.from_file(...)` reads the YAML, substitutes
# MAGIC `${var.NAME}` references with `params`, and `as_graph()` compiles
# MAGIC it into a LangGraph workflow.

# COMMAND ----------

from dao_ai.config import AppConfig

config: AppConfig = AppConfig.from_file("greeter.yaml", params=params)
agent: CompiledStateGraph = config.as_graph()

print(f"Compiled app name: {config.app.name}")
try:
    config.display_graph()
except Exception as e:
    print(f"An exception has occurred: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- Test locally
# MAGIC
# MAGIC `config.as_graph()` returns a LangGraph `CompiledStateGraph`. You
# MAGIC can drive it directly with `agent.ainvoke(...)`, which is what
# MAGIC every previous example uses.

# COMMAND ----------

response: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "Hi! Is this thing on?"}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4a. Same agent, ResponsesAgent shape
# MAGIC
# MAGIC `config.as_responses_agent()` wraps the same compiled graph as
# MAGIC the OpenAI-style **ResponsesAgent** that the deployed app exposes
# MAGIC at `/invocations`. Pair it with `process_messages(...)` from
# MAGIC `dao_ai.models` to get a normalized payload (chat-completions
# MAGIC list, MLflow message dicts, or plain `{"input": [...]}` all work).
# MAGIC This is the easiest way to mirror the production endpoint while
# MAGIC iterating in a notebook.

# COMMAND ----------

from dao_ai.models import process_messages
from mlflow.pyfunc import ResponsesAgent
from mlflow.types.responses import ResponsesAgentResponse

responses_agent: ResponsesAgent = config.as_responses_agent()
result: ResponsesAgentResponse = process_messages(
    responses_agent,
    [{"role": "user", "content": "In one sentence, what's a DAO-AI agent?"}],
)
print(result.output[-1].content[0].text)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 -- Deploy as a Databricks App
# MAGIC
# MAGIC `config.deploy_agent(target=DeploymentTarget.APPS)` generates the
# MAGIC Asset Bundle from the dao-ai config and deploys + runs it as a
# MAGIC Databricks App in one call.

# COMMAND ----------

from dao_ai.config import DeploymentTarget

config.deploy_agent(target=DeploymentTarget.APPS)
print(f"Deployed app: {config.app.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next
# MAGIC
# MAGIC [Chapter 2](../lab-2-uc-tools/) -- give the agent
# MAGIC real tools (Unity Catalog SQL functions) so it stops guessing
# MAGIC about products and queries a governed table instead.
