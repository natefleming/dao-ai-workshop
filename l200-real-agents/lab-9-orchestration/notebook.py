# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 9 -- Multi-agent Orchestration
# MAGIC
# MAGIC **Level:** L200
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Declare three specialist agents (`tier1_support`, `tier2_engineer`, `escalation_lead`) with distinct prompts and `handoff_prompt:` strings.
# MAGIC - Wire them under a **supervisor** that routes per turn, then under a **swarm** with mixed deterministic + agentic handoffs.
# MAGIC - See how the same specialists work under both orchestration patterns.
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC A `tier-routing` app where a refund question routes to escalation, a 500-error question routes to tier-2, and a how-to question routes to tier-1 -- all from one user input each.

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

dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-4-5", "LLM endpoint")

params: dict[str, str] = {
    "username": username,
    "llm_endpoint": dbutils.widgets.get("llm_endpoint").strip(),
}

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC # Part A -- Supervisor Pattern

# COMMAND ----------

from dao_ai.config import AppConfig

config: AppConfig = AppConfig.from_file("specialists_with_supervisor.yaml", params=params)
agent: CompiledStateGraph = config.as_graph()

print(f"Compiled app name: {config.app.name}")
try:
    config.display_graph()
except Exception as e:
    print(f"An exception has occurred: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### How-to question -> tier1_support

# COMMAND ----------

response: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "How do I export my conversation history?"}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Bug report -> tier2_engineer

# COMMAND ----------

response: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "I'm getting a 500 error from your API since yesterday's deploy."}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Refund request -> escalation_lead

# COMMAND ----------

response: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "I was double-charged last month. Can I get a refund?"}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC # Part B -- Swarm with Directed Routes

# COMMAND ----------

swarm_config: AppConfig = AppConfig.from_file("specialists_with_swarm.yaml", params=params)
swarm_agent: CompiledStateGraph = swarm_config.as_graph()
try:
    swarm_config.display_graph()
except Exception as e:
    print(f"An exception has occurred: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Mixed-intent question: triage -> tier2 (deterministic) -> escalation (agentic)

# COMMAND ----------

response: dict[str, Any] = await swarm_agent.ainvoke(
    {"messages": [{"role": "user", "content": "Our webhook deliveries have been failing for a week, and I want a credit for the downtime."}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 -- Deploy as a Databricks App
# MAGIC
# MAGIC Deploys the supervisor variant. Swap `config` for `swarm_config`
# MAGIC to deploy the swarm variant instead.

# COMMAND ----------

from dao_ai.config import DeploymentTarget

config.deploy_agent(target=DeploymentTarget.APPS)
print(f"Deployed app: {config.app.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Congratulations!
# MAGIC
# MAGIC You've completed the workshop. The chapters covered:
# MAGIC
# MAGIC | Use case | Chapters | dao-ai concepts |
# MAGIC |---|---|---|
# MAGIC | Hardware-store retail | 1-4 | LLM agent, UC function tools, Genie, MCP |
# MAGIC | SaaS helpdesk | 5-9 | REST tools, vector search + reranker, memory, prompts + guardrails, multi-agent |
# MAGIC
# MAGIC **Want more?** See [`l300-advanced/`](../../l300-advanced/) for two
# MAGIC more advanced patterns: instructed retrieval (Lab 10) and Genie
# MAGIC context-aware caching with L1 LRU + L2 similarity layers (Lab 11).
