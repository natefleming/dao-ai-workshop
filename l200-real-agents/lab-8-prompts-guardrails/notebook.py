# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 8 -- Production Prompts and Guardrails
# MAGIC
# MAGIC **Level:** L200
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Move an inline prompt into MLflow Prompt Registry via the `prompts:` block.
# MAGIC - Edit the prompt in the MLflow UI and watch the agent pick up the new version on next load.
# MAGIC - Add a `guardrails:` block with a judge LLM that evaluates response **accuracy** and retries on failure.
# MAGIC - Inspect nested guardrail spans in the MLflow trace.
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC A `safe-support` agent that, when asked for a critical-ticket SLA it doesn't know, says so honestly instead of inventing one -- with a `accuracy_check` span visible in the trace.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 -- Install dependencies

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.58"
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
dbutils.widgets.text("judge_llm_endpoint", "databricks-claude-sonnet-4-5", "Judge LLM endpoint")

catalog: str = dbutils.widgets.get("catalog").strip()
if not catalog:
    raise ValueError("Set the catalog widget at the top of the notebook.")

params: dict[str, str] = {
    "username": username,
    "catalog": catalog,
    "schema": dbutils.widgets.get("schema").strip(),
    "llm_endpoint": dbutils.widgets.get("llm_endpoint").strip(),
    "judge_llm_endpoint": dbutils.widgets.get("judge_llm_endpoint").strip(),
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 -- Provision shared resources

# COMMAND ----------

from dao_ai.config import AppConfig

final_config: AppConfig = AppConfig.from_file("03_support_with_guardrails.yaml", params=params)

for schema in final_config.schemas.values():
    schema.create()
    print(f"Schema ready: {schema.full_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- Walk the steps

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4a. `01_inline_support.yaml` -- inline prompt

# COMMAND ----------

config_step1: AppConfig = AppConfig.from_file("01_inline_support.yaml", params=params)
agent_step1: CompiledStateGraph = config_step1.as_graph()

response: dict[str, Any] = await agent_step1.ainvoke(
    {"messages": [{"role": "user", "content": "What's the SLA for critical support tickets?"}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4b. `02_support_with_managed_prompts.yaml`
# MAGIC
# MAGIC `as_graph()` auto-registers the prompt as version 1 the first
# MAGIC time it runs. Open the **Prompts** tab in MLflow to confirm.

# COMMAND ----------

config_step2: AppConfig = AppConfig.from_file("02_support_with_managed_prompts.yaml", params=params)
agent_step2: CompiledStateGraph = config_step2.as_graph()

response: dict[str, Any] = await agent_step2.ainvoke(
    {"messages": [{"role": "user", "content": "What's the SLA for critical support tickets?"}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4c. `03_support_with_guardrails.yaml` -- accuracy guardrail (final)
# MAGIC
# MAGIC The judge runs after every response. If the agent fabricates a
# MAGIC specific SLA number or policy, the judge fails the response and
# MAGIC the agent retries. Watch the MLflow trace for nested
# MAGIC `accuracy_check` spans.

# COMMAND ----------

config: AppConfig = AppConfig.from_file("03_support_with_guardrails.yaml", params=params)
agent: CompiledStateGraph = config.as_graph()
try:
    config.display_graph()
except Exception as e:
    print(f"An exception has occurred: {e}")

# COMMAND ----------

response: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "What's the SLA for critical support tickets?"}]},
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
# MAGIC [Chapter 9](../lab-9-orchestration/) -- multi-agent: tier-1 / tier-2 /
# MAGIC escalation specialists with supervisor or swarm orchestration.
