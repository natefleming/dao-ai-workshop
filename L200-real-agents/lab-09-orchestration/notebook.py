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
# MAGIC - Finish with a **smart model routing** variant: a tiny router supervisor picks between a fast/cheap agent and a larger reasoning agent based on prompt complexity.
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC A `tier-routing` app where a refund question routes to escalation, a 500-error question routes to tier-2, and a how-to question routes to tier-1 -- all from one user input each. Plus a `smart-routing` app that sends easy questions to a small model and hard ones to a large model.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 -- Install dependencies

# COMMAND ----------

# MAGIC %uv pip install "dao-ai==0.2.4"
# MAGIC %restart_python

# COMMAND ----------

from importlib.metadata import version

print(f"dao-ai={version('dao-ai')}")

import nest_asyncio
nest_asyncio.apply()

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

dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-4-5", "Primary LLM (escalation_lead)")
dbutils.widgets.text("fast_llm_endpoint", "databricks-claude-haiku-4-5", "Fast LLM (tier1_support)")
dbutils.widgets.text("technical_llm_endpoint", "databricks-meta-llama-3-1-8b-instruct", "Technical LLM (tier2_engineer)")

# Smart-routing variant (Part C) parameters.
dbutils.widgets.text("router_llm_endpoint", "databricks-claude-haiku-4-5", "Router LLM (smart-routing supervisor)")
dbutils.widgets.text("simple_llm_endpoint", "databricks-claude-haiku-4-5", "Simple LLM (simple_agent)")
dbutils.widgets.text("complex_llm_endpoint", "databricks-claude-sonnet-4-5", "Complex LLM (complex_agent)")

# Spreading agents across multiple endpoints reduces per-endpoint rate-limit
# pressure when the supervisor or swarm fans out across specialists in one turn.
params: dict[str, str] = {
    "username": username,
    "llm_endpoint": dbutils.widgets.get("llm_endpoint").strip(),
    "fast_llm_endpoint": dbutils.widgets.get("fast_llm_endpoint").strip(),
    "technical_llm_endpoint": dbutils.widgets.get("technical_llm_endpoint").strip(),
    "router_llm_endpoint": dbutils.widgets.get("router_llm_endpoint").strip(),
    "simple_llm_endpoint": dbutils.widgets.get("simple_llm_endpoint").strip(),
    "complex_llm_endpoint": dbutils.widgets.get("complex_llm_endpoint").strip(),
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
# MAGIC ### Streamed swarm: see each handoff arrive as it happens
# MAGIC
# MAGIC `config.as_responses_agent()` + `process_messages_stream` lets us
# MAGIC observe the swarm work in real time -- you'll see tier-1 triage,
# MAGIC the handoff event, the tier-2 (or escalation) specialist, and any
# MAGIC follow-up handoff arrive as separate stream events instead of
# MAGIC waiting for the full conversation. This is the same shape the
# MAGIC deployed app's `/invocations` endpoint produces under
# MAGIC `?stream=true` / SSE.

# COMMAND ----------

from dao_ai.models import process_messages_stream
from mlflow.pyfunc import ResponsesAgent
from mlflow.types.responses import ResponsesAgentStreamEvent

swarm_responses: ResponsesAgent = swarm_config.as_responses_agent()
event: ResponsesAgentStreamEvent
for event in process_messages_stream(
    swarm_responses,
    [{"role": "user", "content": "How do I export my data, and can I get a discount for the trouble?"}],
):
    delta: str | None = getattr(event, "delta", None)
    if delta:
        print(delta, end="", flush=True)
print()

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC # Part C -- Smart Model Routing
# MAGIC
# MAGIC Same supervisor pattern as Part A, but the two specialists are
# MAGIC differentiated by **model size** rather than by domain role. A
# MAGIC tiny router supervisor decides which one answers:
# MAGIC
# MAGIC - `simple_agent`  -- cheap/fast model for everyday questions.
# MAGIC - `complex_agent` -- larger reasoning model for multi-step problems.
# MAGIC
# MAGIC This is a common cost-optimization pattern: don't spend
# MAGIC reasoning-model dollars on questions a small model can answer
# MAGIC in one shot. Every model call flows through the Unity AI
# MAGIC Gateway (`ai_gateway: true`) for rate limiting and audit.

# COMMAND ----------

routing_config: AppConfig = AppConfig.from_file("smart_routing.yaml", params=params)
routing_agent: CompiledStateGraph = routing_config.as_graph()

print(f"Compiled app name: {routing_config.app.name}")
try:
    routing_config.display_graph()
except Exception as e:
    print(f"An exception has occurred: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Simple question -> simple_agent (small/fast model)

# COMMAND ----------

response: dict[str, Any] = await routing_agent.ainvoke(
    {"messages": [{"role": "user", "content": "What is the capital of France?"}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Complex question -> complex_agent (larger reasoning model)

# COMMAND ----------

response: dict[str, Any] = await routing_agent.ainvoke(
    {
        "messages": [
            {
                "role": "user",
                "content": (
                    "Two trains leave stations 300 miles apart at the same time, "
                    "heading toward each other. Train A travels at 60 mph and "
                    "train B at 40 mph. How far from A's station do they meet, "
                    "and how long does it take? Show your reasoning."
                ),
            }
        ]
    },
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Streamed routing: watch the supervisor pick and the chosen agent answer

# COMMAND ----------

routing_responses: ResponsesAgent = routing_config.as_responses_agent()
for event in process_messages_stream(
    routing_responses,
    [
        {
            "role": "user",
            "content": (
                "Compare snapshot isolation and serializable isolation for a "
                "payments ledger that fans out to three downstream services. "
                "Which do you pick and why?"
            ),
        }
    ],
):
    delta: str | None = getattr(event, "delta", None)
    if delta:
        print(delta, end="", flush=True)
print()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 -- Deploy as a Databricks App
# MAGIC
# MAGIC Deploys the smart-routing variant. Swap `routing_config` for
# MAGIC `config` (supervisor) or `swarm_config` (swarm) to deploy either
# MAGIC of the other patterns.

# COMMAND ----------

from dao_ai.config import ServingMode

routing_config.deploy_agent(target=ServingMode.APPS)
print(f"Deployed app: {routing_config.app.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next
# MAGIC
# MAGIC [Lab 10 -- Human in the Loop](../lab-10-hitl/) -- gate the
# MAGIC refund tool with `human_in_the_loop:` and resume the workflow
# MAGIC on a human's approve / edit / reject decision.
