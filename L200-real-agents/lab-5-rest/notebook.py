# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 5 -- External Integrations via REST
# MAGIC
# MAGIC **Level:** L200
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Use `dao_ai.tools.create_rest_api_tool` to wrap a public HTTP endpoint as an agent tool.
# MAGIC - Switch domain framing from hardware-store retail to a SaaS support helpdesk.
# MAGIC - See how a support agent can triage upstream-vendor outages by calling a real status API.
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC A `status-check` agent that answers `"Is GitHub having an outage right now?"` by calling `https://www.githubstatus.com/api/v2/status.json`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 -- Install dependencies

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.64"
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

dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-4-5", "LLM endpoint")

params: dict[str, str] = {
    "username": username,
    "llm_endpoint": dbutils.widgets.get("llm_endpoint").strip(),
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 -- Build the agent

# COMMAND ----------

from dao_ai.config import AppConfig

config: AppConfig = AppConfig.from_file("status_check.yaml", params=params)
agent: CompiledStateGraph = config.as_graph()

print(f"Compiled app name: {config.app.name}")
try:
    config.display_graph()
except Exception as e:
    print(f"An exception has occurred: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- Test locally

# COMMAND ----------

response: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "Is GitHub having an outage right now?"}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4a. Stream the same answer (ResponsesAgent + `process_messages_stream`)
# MAGIC
# MAGIC `config.as_responses_agent()` returns the same OpenAI-style
# MAGIC ResponsesAgent the deployed app exposes at `/invocations`.
# MAGIC `process_messages_stream(...)` from `dao_ai.models` runs it in
# MAGIC streaming mode and yields incremental events as the agent thinks
# MAGIC and the REST tool returns. Useful when the upstream call (here:
# MAGIC GitHub Status) takes a moment and you want to surface partial
# MAGIC progress in a UI.

# COMMAND ----------

from dao_ai.models import process_messages_stream
from mlflow.pyfunc import ResponsesAgent
from mlflow.types.responses import ResponsesAgentStreamEvent

responses_agent: ResponsesAgent = config.as_responses_agent()
event: ResponsesAgentStreamEvent
for event in process_messages_stream(
    responses_agent,
    [{"role": "user", "content": "Walk me through the latest GitHub status incidents in 2 sentences."}],
):
    delta: str | None = getattr(event, "delta", None)
    if delta:
        print(delta, end="", flush=True)
print()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 -- Deploy as a Databricks App

# COMMAND ----------

from dao_ai.config import DeploymentTarget

config.deploy_agent(target=DeploymentTarget.APPS)
print(f"Deployed app: {config.app.name}")
