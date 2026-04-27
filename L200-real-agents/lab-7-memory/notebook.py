# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 7 -- Persistent Memory
# MAGIC
# MAGIC **Level:** L200
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Configure a Lakebase-backed `memory.checkpointer:` for thread-scoped state that survives restarts.
# MAGIC - Add a `memory.store:` + `memory.extraction:` so structured facts persist across threads for the same `user_id`.
# MAGIC - Verify the agent recalls a customer's prior context across a brand-new thread.
# MAGIC - Add `app.chat_history:` so long conversations get summarized automatically once they exceed the token budget.
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC A `support-history-<your-username>` agent where Jordan opens a new thread and the agent recalls the prior issue (e.g. `"You were investigating a 401 error -- did that resolve?"`), and a long thread that triggers chat-history summarization mid-conversation.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 -- Install dependencies

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.61"
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
# user_id must be a valid namespace label (no periods). Sanitize to letters/digits/hyphens.
user_id: str = re.sub(r"[^a-z0-9]+", "-", w.current_user.me().user_name.lower()).strip("-")
print(f"Derived username: {username} (user_id={user_id})")

dbutils.widgets.text("lakebase_name", "retail-consumer-goods", "Lakebase instance")
dbutils.widgets.text("lakebase_project", "retail-consumer-goods", "Lakebase project")
dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-4-5", "LLM endpoint")
# Lower-than-default summarization thresholds so the demo triggers within a handful of turns.
dbutils.widgets.text("max_tokens_before_summary", "1500", "Summarization trigger (low for demo)")
dbutils.widgets.text("max_tokens_after_summary", "500", "Kept budget after summary (low for demo)")

params: dict[str, str] = {
    "username": username,
    "lakebase_name": dbutils.widgets.get("lakebase_name").strip(),
    "lakebase_project": dbutils.widgets.get("lakebase_project").strip(),
    "llm_endpoint": dbutils.widgets.get("llm_endpoint").strip(),
    "max_tokens_before_summary": dbutils.widgets.get("max_tokens_before_summary").strip(),
    "max_tokens_after_summary": dbutils.widgets.get("max_tokens_after_summary").strip(),
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 -- Build the agent
# MAGIC
# MAGIC `support_assistant.yaml` declares two memory layers and a
# MAGIC summarization rule:
# MAGIC
# MAGIC ```yaml
# MAGIC resources:
# MAGIC   databases:
# MAGIC     workshop_db: { name: ${var.lakebase_name}, project: ${var.lakebase_project} }
# MAGIC
# MAGIC memory:
# MAGIC   checkpointer:
# MAGIC     database: *workshop_db                  # short-term: scoped to thread_id
# MAGIC   store:
# MAGIC     database: *workshop_db
# MAGIC     namespace: "{user_id}"                  # long-term: scoped to user
# MAGIC   extraction:
# MAGIC     schemas: [user_profile, preference]
# MAGIC     auto_inject: true                       # injects extracted facts into the prompt
# MAGIC
# MAGIC app:
# MAGIC   chat_history:                             # auto-summarize when thread gets long
# MAGIC     model: *summarization_llm
# MAGIC     max_tokens: ${var.max_tokens_after_summary}
# MAGIC     max_tokens_before_summary: ${var.max_tokens_before_summary}
# MAGIC ```

# COMMAND ----------

from dao_ai.config import AppConfig

config: AppConfig = AppConfig.from_file("support_assistant.yaml", params=params)
agent: CompiledStateGraph = config.as_graph()

print(f"Compiled app name: {config.app.name}")
try:
    config.display_graph()
except Exception as e:
    print(f"An exception has occurred: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- Test cross-session memory
# MAGIC
# MAGIC Establish a fact in thread A. Open a brand-new thread B with the
# MAGIC **same** `user_id`. The store + extraction pipeline should let
# MAGIC the agent recall the earlier context.

# COMMAND ----------

await agent.ainvoke(
    {"messages": [{"role": "user", "content": "I'm Jordan. I'm getting 401 errors on the API since 09:00 today."}]},
    config={"configurable": {"thread_id": f"lab7-thread-A-{username}", "user_id": user_id}},
)
print("Fact established in thread A.")

# COMMAND ----------

resp: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "Do you remember what error I was investigating?"}]},
    config={"configurable": {"thread_id": f"lab7-thread-B-{username}", "user_id": user_id}},
)
print(resp["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 -- Test chat-history summarization
# MAGIC
# MAGIC We deliberately set `max_tokens_before_summary` low (1500) so
# MAGIC summarization fires within a few turns. Track the message count
# MAGIC after each turn -- it drops once the summary replaces older
# MAGIC turns.

# COMMAND ----------

thread_id: str = f"lab7-summary-{username}"
turns = [
    "Hi, I'm Jordan. I'm getting intermittent 500 errors from your /v1/conversations endpoint.",
    "The errors started this morning around 09:00 UTC, after we deployed our 4.2 release.",
    "We're seeing maybe 1 in 20 requests fail. The successful ones look normal.",
    "Our retry logic handles it for now, but it's making our dashboards look noisy.",
    "Could this be related to the recent api-gateway upgrade you mentioned in the changelog?",
    "What logs should I pull from our side to help you investigate?",
    "Summarize what we've covered so far, and what the next step is.",
]

for i, content in enumerate(turns, 1):
    resp = await agent.ainvoke(
        {"messages": [{"role": "user", "content": content}]},
        config={"configurable": {"thread_id": thread_id, "user_id": user_id}},
    )
    msg_count = len(resp["messages"])
    last = resp["messages"][-1].content
    print(f"=== Turn {i} (messages in state: {msg_count}) ===")
    print(last[:200] + ("..." if len(last) > 200 else ""))
    print()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 -- Deploy as a Databricks App

# COMMAND ----------

from dao_ai.config import DeploymentTarget

config.deploy_agent(target=DeploymentTarget.APPS)
print(f"Deployed app: {config.app.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next
# MAGIC
# MAGIC [Lab 8](../lab-8-prompts-guardrails/) -- prompts in MLflow
# MAGIC Registry + a judge LLM that retries on quality failures.
