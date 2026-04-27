# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 10 -- Human in the Loop
# MAGIC
# MAGIC **Level:** L200
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Add `human_in_the_loop:` to a UC-function tool so the agent **pauses for human approval** before the tool runs.
# MAGIC - See the workflow interrupt as a structured `__interrupt__` payload, then resume with an **approve / edit / reject** decision.
# MAGIC - Understand why HITL needs a checkpointer (the agent state has to survive the pause), and why DAO-AI's automatic in-memory fallback is fine for the demo but Lakebase is what production uses.
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC A `hitl-refund-<your-username>` agent that, when asked to refund a duplicate charge, pauses with the proposed `(order_id, amount, reason)` arguments. Approving resumes the run and the tool returns; rejecting cancels with feedback the agent then explains.

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
from typing import Any

from databricks.sdk import WorkspaceClient
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

w: WorkspaceClient = WorkspaceClient()
short_name: str = w.current_user.me().user_name.split("@")[0].lower()
username: str = re.sub(r"[^a-z0-9]+", "-", short_name).strip("-")[:13]
print(f"Derived username: {username}")

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
# MAGIC ## Step 3 -- The HITL wiring in YAML
# MAGIC
# MAGIC The interesting block is on the tool, not the agent:
# MAGIC
# MAGIC ```yaml
# MAGIC tools:
# MAGIC   issue_refund_tool: &issue_refund_tool
# MAGIC     name: issue_refund
# MAGIC     function:
# MAGIC       type: unity_catalog
# MAGIC       schema: *workshop_schema
# MAGIC       name: issue_refund
# MAGIC       human_in_the_loop:
# MAGIC         review_prompt: |
# MAGIC           The agent is requesting to issue a refund...
# MAGIC         allowed_decisions: [approve, edit, reject]
# MAGIC ```
# MAGIC
# MAGIC `human_in_the_loop:` works on **any** tool type (UC function, MCP, factory, REST). It maps to LangChain's `HumanInTheLoopMiddleware`, which auto-wraps the tool so the LangGraph workflow pauses before execution. The agent definition itself doesn't change -- HITL is a tool-level concern.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3a. Load and provision

# COMMAND ----------

from dao_ai.config import AppConfig

config: AppConfig = AppConfig.from_file("support_with_hitl.yaml", params=params)

for s in config.schemas.values():
    s.create()
    print(f"Schema ready:    {s.full_name}")

for uc_fn in config.unity_catalog_functions:
    uc_fn.create()
    print(f"Function ready:  {uc_fn.function.full_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3b. Compile the agent
# MAGIC
# MAGIC HITL needs a checkpointer (state must survive the pause). DAO-AI auto-falls-back to an in-memory checkpointer when HITL is enabled and no `memory.checkpointer.database` is configured -- good enough for this demo. Production should use Lakebase (see Lab 7).

# COMMAND ----------

agent: CompiledStateGraph = config.as_graph()

print(f"Compiled app name: {config.app.name}")
try:
    config.display_graph()
except Exception as e:
    print(f"display_graph: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- See the interrupt
# MAGIC
# MAGIC Send a refund request. The agent will gather arguments and call `issue_refund` -- which is HITL-gated, so the workflow pauses and surfaces an interrupt instead of running the tool.

# COMMAND ----------

thread_config: dict[str, Any] = {"configurable": {"thread_id": f"lab10-{username}"}}

response: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": (
        "Hi, I was charged $49.99 twice for order ORD-1234 -- I'd like a refund "
        "of $49.99 for the duplicate charge."
    )}]},
    config=thread_config,
)

interrupts: list[Any] = response.get("__interrupt__", [])
print(f"interrupts surfaced: {len(interrupts)}")
for intr in interrupts:
    print(intr)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 -- Approve and resume
# MAGIC
# MAGIC The interrupt payload describes the action the agent wants to take. We resume the run with a `Command(resume={"decisions": [...]})` carrying the human's decision(s) -- one per pending action. The decision types are `ApproveDecision()`, `EditDecision(args=...)`, or `RejectDecision(message=...)` from `langchain.agents.middleware.human_in_the_loop`.

# COMMAND ----------

# Decisions are plain TypedDicts: {"type": "approve" | "edit" | "reject"}
# with optional "message" (reject) or "edited_action" (edit). The HITL
# middleware reads decision["type"] -- always populate the type key.

approve_response: dict[str, Any] = await agent.ainvoke(
    Command(resume={"decisions": [{"type": "approve"}]}),
    config=thread_config,
)
print(approve_response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 -- Reject on a different thread
# MAGIC
# MAGIC New thread, same prompt -- this time we reject the refund and pass feedback the agent must explain back to the customer. Notice we use a fresh `thread_id` so the rejection doesn't tangle with the approved run.

# COMMAND ----------

reject_thread: dict[str, Any] = {"configurable": {"thread_id": f"lab10-{username}-reject"}}

response = await agent.ainvoke(
    {"messages": [{"role": "user", "content": (
        "I want a refund for order ORD-9999, $200.00 -- not happy with the product."
    )}]},
    config=reject_thread,
)
print(f"interrupts surfaced: {len(response.get('__interrupt__', []))}")

# COMMAND ----------

reject_response: dict[str, Any] = await agent.ainvoke(
    Command(resume={"decisions": [{
        "type": "reject",
        "message": (
            "Refunds over $100 require manager approval. Tell the customer this "
            "needs to be escalated and ask if they'd like a credit instead."
        ),
    }]}),
    config=reject_thread,
)
print(reject_response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6b -- Edit the proposed arguments
# MAGIC
# MAGIC `EditDecision(args=...)` lets the human modify the tool's
# MAGIC arguments before execution. Useful when the agent picked the
# MAGIC right tool but got a number wrong.

# COMMAND ----------

edit_thread: dict[str, Any] = {"configurable": {"thread_id": f"lab10-{username}-edit"}}

response = await agent.ainvoke(
    {"messages": [{"role": "user", "content": (
        "Refund order ORD-5555 for $99.99 -- the discount code didn't apply."
    )}]},
    config=edit_thread,
)
print(f"interrupts surfaced: {len(response.get('__interrupt__', []))}")

edit_response: dict[str, Any] = await agent.ainvoke(
    Command(resume={"decisions": [{
        "type": "edit",
        "edited_action": {
            "name": "issue_refund",
            "args": {
                "order_id": "ORD-5555",
                # Reviewer cuts the refund in half because the discount was 50%, not full.
                "amount": 49.99,
                "reason": "discount code partial-apply (corrected by reviewer)",
            },
        },
    }]}),
    config=edit_thread,
)
print(edit_response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 -- Deploy as a Databricks App
# MAGIC
# MAGIC When the agent runs as a Databricks App, the deployed `/invocations` endpoint surfaces interrupts via `response.custom_outputs["interrupts"]`. Your client UI is responsible for showing the action-request to a human, collecting their decision, and resuming the run by sending it back as `custom_inputs.resume`. The `support_with_hitl.yaml` agent ships exactly this shape so a chat UI built on the standard ResponsesAgent contract just works.

# COMMAND ----------

from dao_ai.config import DeploymentTarget

config.deploy_agent(target=DeploymentTarget.APPS)
print(f"Deployed app: {config.app.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next
# MAGIC
# MAGIC You've finished the L200 sequence -- nine production patterns over the saas_helpdesk theme. [`L300-advanced/`](../../L300-advanced/) covers three advanced patterns: instructed retrieval (Lab 11), Genie context-aware caching (Lab 12), and programmatic construction (Lab 13).
