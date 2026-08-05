# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 21 -- User Feedback on Agent Responses
# MAGIC
# MAGIC **Level:** L300
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Read the outer MLflow `trace_id` from `response.custom_outputs["trace_id"]`.
# MAGIC - Attach a thumbs-up / thumbs-down assessment using
# MAGIC   `dao_ai.evaluation.log_user_feedback(...)`.
# MAGIC - Verify the assessment lands on the OUTER multi-agent trace via
# MAGIC   `mlflow.search_traces`.
# MAGIC
# MAGIC ## Why this matters
# MAGIC
# MAGIC In multi-agent flows the trace_id you want for feedback is the OUTER
# MAGIC root trace -- the one whose children include every sub-agent hop. dao-ai
# MAGIC exposes that trace_id on `custom_outputs` so the caller never has to
# MAGIC read it from MLflow global state, which races under concurrency and
# MAGIC returns `None` after the agent function returns.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 -- Install dependencies

# COMMAND ----------

# MAGIC %uv pip install "dao-ai==0.2.5"
# MAGIC %restart_python

# COMMAND ----------

from importlib.metadata import version

print(f"dao-ai={version('dao-ai')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 -- Configure parameters

# COMMAND ----------

import asyncio
import os
import re

import nest_asyncio

# Notebook runs inside an active event loop; nest_asyncio lets us call
# asyncio.run(...) on the agent's coroutine without recursing into uvloop.
nest_asyncio.apply()

# Force synchronous trace export so the demo's tight loop (invoke -> log
# feedback in the next cell) is deterministic. Must be set BEFORE
# importing mlflow.
os.environ["MLFLOW_ENABLE_ASYNC_TRACE_LOGGING"] = "false"

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w: WorkspaceClient = WorkspaceClient()
short_name: str = w.current_user.me().user_name.split("@")[0].lower()
username: str = re.sub(r"[^a-z0-9]+", "-", short_name).strip("-")[:13]
USER: str = w.current_user.me().user_name
print(f"username: {username}")
print(f"user_id:  {USER}")

dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-4-5", "Default LLM")
dbutils.widgets.text(
    "fast_llm_endpoint", "databricks-claude-haiku-4-5", "Fast LLM (tier-1)"
)

params: dict[str, str] = {
    "username": username,
    "llm_endpoint": dbutils.widgets.get("llm_endpoint").strip(),
    "fast_llm_endpoint": dbutils.widgets.get("fast_llm_endpoint").strip(),
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 -- Build the agent

# COMMAND ----------

import mlflow

from dao_ai.config import AppConfig
from dao_ai.evaluation import log_user_feedback

# Autolog opens the langchain root trace. Combined with dao-ai 0.1.87's
# @mlflow.trace decorator on apredict, the trace_id we read from
# custom_outputs is always the OUTER multi-agent root.
mlflow.langchain.autolog()

config: AppConfig = AppConfig.from_file("feedback_agent.yaml", params=params)
agent = config.as_responses_agent()
print(f"App: {config.app.name}")
print(f"Agents: {[a.name for a in config.app.agents]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- Invoke + log thumbs-up
# MAGIC
# MAGIC 1. Build a `ResponsesAgentRequest`.
# MAGIC 2. `await agent.apredict(request)` -- the `@mlflow.trace` decorator opens the outer trace.
# MAGIC 3. Pull `trace_id` from `response.custom_outputs["trace_id"]`.
# MAGIC 4. Call `log_user_feedback(trace_id=..., value="up", ...)`.

# COMMAND ----------

from mlflow.types.responses import ResponsesAgentRequest

req_positive = ResponsesAgentRequest(
    input=[
        {"role": "user", "content": "How do I export my account data?"}
    ],
    custom_inputs={
        "configurable": {"user_id": USER},
        "session": {},
    },
)

resp_positive = asyncio.run(agent.apredict(req_positive))
trace_id_positive: str = resp_positive.custom_outputs["trace_id"]
print("assistant:", resp_positive.output[0].model_dump()["content"][0]["text"][:300])
print("trace_id: ", trace_id_positive)

log_user_feedback(
    trace_id=trace_id_positive,
    value="up",
    comment="Helpful answer, exactly what I needed.",
    user_id=USER,
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 -- Invoke + log thumbs-down
# MAGIC
# MAGIC Same contract; this turn routes through `tier2_engineer`, so the
# MAGIC outer trace has different sub-agent children, but the
# MAGIC `custom_outputs["trace_id"]` field still points at the root.

# COMMAND ----------

req_negative = ResponsesAgentRequest(
    input=[
        {
            "role": "user",
            "content": "Webhook deliveries are failing with HTTP 500. Where do I start?",
        }
    ],
    custom_inputs={
        "configurable": {"user_id": USER},
        "session": {},
    },
)

resp_negative = asyncio.run(agent.apredict(req_negative))
trace_id_negative: str = resp_negative.custom_outputs["trace_id"]
print("assistant:", resp_negative.output[0].model_dump()["content"][0]["text"][:300])
print("trace_id: ", trace_id_negative)

log_user_feedback(
    trace_id=trace_id_negative,
    value="down",
    comment="Answer was too generic -- no concrete next step.",
    user_id=USER,
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 -- Verify the trace is the OUTER multi-agent root

# COMMAND ----------

for label, tid in [("positive", trace_id_positive), ("negative", trace_id_negative)]:
    trace = mlflow.get_trace(tid)
    spans = trace.search_spans()
    root = next((s for s in spans if s.parent_id is None), None)
    handoffs = sorted({s.name for s in spans if s.name and "handoff_to_" in s.name})
    assess_names = [a.name for a in (trace.info.assessments or [])]
    print(
        f"[{label}] trace_id={tid}\n"
        f"  spans={len(spans)} root={(root.name, root.span_type) if root else None}\n"
        f"  sub-agent handoffs: {handoffs}\n"
        f"  assessments: {assess_names}"
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 -- Query traces with feedback via SQL

# COMMAND ----------

traces = mlflow.search_traces(max_results=50)
print(f"total traces: {len(traces)}")
spark.createDataFrame(traces).createOrReplaceTempView("feedback_lab_traces")

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT
# MAGIC   trace_id,
# MAGIC   a.feedback.value      AS feedback_value,
# MAGIC   a.rationale           AS comment,
# MAGIC   a.source.source_id    AS user_id
# MAGIC FROM feedback_lab_traces
# MAGIC LATERAL VIEW EXPLODE(assessments) AS a
# MAGIC WHERE a.assessment_name = 'user_feedback'
# MAGIC ORDER BY request_time DESC

# COMMAND ----------

# MAGIC %md
# MAGIC ## What you just did
# MAGIC
# MAGIC | Step | Action |
# MAGIC |---|---|
# MAGIC | 5 | Invoked the multi-agent supervisor in-process, read trace_id from `custom_outputs`, logged thumbs-up |
# MAGIC | 6 | Same flow for a thumbs-down on a technical-routed turn |
# MAGIC | 7 | Verified the trace_id maps to the OUTER root (`AGENT|predict`) not a sub-agent leg |
# MAGIC | 8 | Queried the assessments via `mlflow.search_traces` and Spark SQL |
# MAGIC
# MAGIC The same `custom_outputs["trace_id"]` contract holds for the deployed
# MAGIC Model Serving endpoint and for the Databricks App `/invocations` route --
# MAGIC `log_user_feedback` works against any of them.
