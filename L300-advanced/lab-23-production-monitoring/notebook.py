# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 23 -- Production Monitoring with Registered Scorers
# MAGIC
# MAGIC **Level:** L300
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Declare an `app.monitoring` block on a dao-ai agent and inspect what
# MAGIC   the YAML produced.
# MAGIC - Register the scorers via `dao_ai.evaluation.register_monitoring_scorers`
# MAGIC   so they run continuously against new traces.
# MAGIC - Drive a small amount of traffic at the in-process agent, then verify
# MAGIC   the scorers' assessments land on the traces via `mlflow.search_traces`.
# MAGIC - Inspect the assessment values + rationales with one Spark SQL query.
# MAGIC - Clean up with `stop_monitoring_scorers()` (vs. `delete_monitoring_scorers()`).
# MAGIC
# MAGIC ## Why this matters
# MAGIC
# MAGIC Offline evaluation (Lab 22) tells you how the agent does on a curated
# MAGIC set. Production monitoring tells you how the agent is doing **right
# MAGIC now**, on real traffic, at a sample rate you control. The dao-ai
# MAGIC `app.monitoring` block is a single source of truth for which scorers
# MAGIC run, at what rate, and which custom `Guidelines` judges join them.
# MAGIC `register_monitoring_scorers` reads that block and converges the MLflow
# MAGIC 3 scorer lifecycle to match, idempotently -- so re-running the lab
# MAGIC updates sample rates instead of stacking duplicates.

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
import time

import nest_asyncio

nest_asyncio.apply()

# Synchronous trace export so the demo's "drive traffic -> search traces"
# loop is deterministic. Must be set BEFORE importing mlflow.
os.environ["MLFLOW_ENABLE_ASYNC_TRACE_LOGGING"] = "false"

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w: WorkspaceClient = WorkspaceClient()
short_name: str = w.current_user.me().user_name.split("@")[0].lower()
username: str = re.sub(r"[^a-z0-9]+", "-", short_name).strip("-")[:13]
USER: str = w.current_user.me().user_name
print(f"username: {username}")

dbutils.widgets.text("catalog", "main", "UC catalog")
dbutils.widgets.text("schema", "dao_ai_workshop", "UC schema")
dbutils.widgets.text("warehouse_id", "", "SQL warehouse ID (for UC trace tables)")
dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-4-5", "Default LLM")
dbutils.widgets.text("fast_llm_endpoint", "databricks-claude-haiku-4-5", "Fast LLM (tier-1)")

warehouse_id: str = dbutils.widgets.get("warehouse_id").strip()
if not warehouse_id:
    raise ValueError(
        "warehouse_id widget is required. The lab deploys to Databricks Apps, "
        "and Apps containers cannot reach the default MLflow trace export host "
        "-- traces would be silently dropped. The YAML's app.trace_location "
        "block routes traces through this SQL warehouse to UC OTEL Delta "
        "tables instead. See Lab 24 for the deeper walkthrough."
    )

params: dict[str, str] = {
    "username": username,
    "catalog": dbutils.widgets.get("catalog").strip(),
    "schema": dbutils.widgets.get("schema").strip(),
    "warehouse_id": warehouse_id,
    "llm_endpoint": dbutils.widgets.get("llm_endpoint").strip(),
    "fast_llm_endpoint": dbutils.widgets.get("fast_llm_endpoint").strip(),
}
print(params)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 -- Build the agent and pin an experiment

# COMMAND ----------

import mlflow

from dao_ai.config import AppConfig

mlflow.langchain.autolog()

# Stable named experiment so the scorers attach to a discoverable place.
experiment = mlflow.set_experiment(f"/Users/{USER}/Lab23-monitoring")
experiment_id: str = experiment.experiment_id
print(f"experiment: {experiment.name} ({experiment_id})")

config: AppConfig = AppConfig.from_file("monitoring_agent.yaml", params=params)

for schema in config.schemas.values():
    schema.create()

agent = config.as_responses_agent()
print(f"App: {config.app.name}")
print(f"Agents: {[a.name for a in config.app.agents]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- Inspect the monitoring config from YAML
# MAGIC
# MAGIC `app.monitoring` is a `MonitoringModel` with four fields:
# MAGIC
# MAGIC | Field | What it controls |
# MAGIC |---|---|
# MAGIC | `sample_rate` | Sample rate for the built-in scorers (cheap, 100% by default) |
# MAGIC | `scorers` | Which built-in scorers to enable (names, or `*` for all) |
# MAGIC | `guidelines` | Named `GuidelineModel` entries -> one `Guidelines` scorer each |
# MAGIC | `guidelines_sample_rate` | Sample rate for the LLM-judge `Guidelines` scorers (expensive, 50% by default) |

# COMMAND ----------

from dao_ai.config import MonitoringModel

if not config.app or not config.app.monitoring:
    raise RuntimeError("Expected app.monitoring in the YAML")

monitoring: MonitoringModel = config.app.monitoring
print(f"sample_rate:            {monitoring.sample_rate}")
print(f"scorers (built-in):     {monitoring.scorers}")
print(f"guidelines_sample_rate: {monitoring.guidelines_sample_rate}")
print("guidelines:")
for g in monitoring.guidelines:
    print(f"  - {g.name}: {len(g.guidelines)} rules")
    for rule in g.guidelines:
        print(f"      * {rule}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 -- Register the scorers
# MAGIC
# MAGIC `register_monitoring_scorers` is idempotent. On first run it creates
# MAGIC each scorer at the configured sample rate. On re-run it updates the
# MAGIC sample rates of existing scorers so YAML stays the source of truth.

# COMMAND ----------

from dao_ai.evaluation import register_monitoring_scorers

registered = register_monitoring_scorers(
    monitoring_config=monitoring,
    experiment_id=experiment_id,
    sql_warehouse_id=warehouse_id or None,
)
print(f"Registered {len(registered)} scorers:")
for s in registered:
    print(f"  - {s.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 -- Confirm the scorers are active

# COMMAND ----------

from dao_ai.evaluation import get_monitoring_scorers

for s in get_monitoring_scorers():
    print(f"  {s.name}: sample_rate={getattr(s, 'sample_rate', '?')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 -- Drive traffic at the in-process agent
# MAGIC
# MAGIC Each `agent.apredict(...)` writes a trace into the active experiment.
# MAGIC The registered scorers run asynchronously on the Databricks side; we
# MAGIC sleep briefly afterwards to let assessments land before we query.

# COMMAND ----------

from mlflow.types.responses import ResponsesAgentRequest

prompts: list[tuple[str, str]] = [
    ("tier1", "How do I change my account display name?"),
    ("tier1", "Where can I see my invoices?"),
    ("tier1", "What is your data retention policy for deleted projects?"),
    ("tier2", "Webhook deliveries are failing with HTTP 500. Where do I start?"),
    ("tier2", "Our cron job hits rate limits at 03:00 UTC every day."),
    ("tier2", "Production traffic is hitting HTTP 502 on /v1/sync every few minutes."),
]

trace_ids: list[str] = []
for tier, content in prompts:
    req = ResponsesAgentRequest(
        input=[{"role": "user", "content": content}],
        custom_inputs={"configurable": {"user_id": USER}, "session": {}},
    )
    resp = asyncio.run(agent.apredict(req))
    tid: str = resp.custom_outputs["trace_id"]
    trace_ids.append(tid)
    print(f"[{tier}] trace_id={tid}")

# Give the async monitoring scorers a moment to score the new traces.
# Production monitoring runs out-of-band; this delay is purely for the
# demo's read-after-write loop.
print("Waiting 20s for monitoring scorers to attach assessments...")
time.sleep(20)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 8 -- Verify the assessments landed

# COMMAND ----------

traces = mlflow.search_traces(
    experiment_ids=[experiment_id],
    max_results=50,
)
print(f"total traces: {len(traces)}")

spark.createDataFrame(traces).createOrReplaceTempView("lab23_traces")

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT
# MAGIC   trace_id,
# MAGIC   a.assessment_name             AS scorer,
# MAGIC   a.feedback.value              AS value,
# MAGIC   a.rationale                   AS rationale
# MAGIC FROM lab23_traces
# MAGIC LATERAL VIEW EXPLODE(assessments) AS a
# MAGIC WHERE a.assessment_name IN (
# MAGIC   'Safety', 'RelevanceToQuery', 'ToolCallEfficiency',
# MAGIC   'routing_quality', 'hallucination_guard'
# MAGIC )
# MAGIC ORDER BY request_time DESC, scorer

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 9 -- Cleanup
# MAGIC
# MAGIC | Helper | Effect |
# MAGIC |---|---|
# MAGIC | `stop_monitoring_scorers()` | Sets each scorer's sample rate to 0. Registration is preserved. Re-running `register_monitoring_scorers(...)` will resume them at the configured rates. |
# MAGIC | `delete_monitoring_scorers()` | Removes the scorers entirely from the experiment. Re-running `register_monitoring_scorers(...)` will recreate them from scratch. |
# MAGIC
# MAGIC Stopping is the right default after the lab so the shared workspace
# MAGIC isn't running LLM-judge scorers against your future traces.

# COMMAND ----------

from dao_ai.evaluation import stop_monitoring_scorers

stopped = stop_monitoring_scorers()
print(f"Stopped {len(stopped)} scorers (sample_rate set to 0; registration preserved)")
for s in stopped:
    print(f"  - {s.name}: sample_rate={getattr(s, 'sample_rate', '?')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## What you just did
# MAGIC
# MAGIC | Step | Action |
# MAGIC |---|---|
# MAGIC | 4 | Inspected the `app.monitoring` block parsed out of YAML |
# MAGIC | 5 | Registered the configured scorers against the MLflow experiment |
# MAGIC | 6 | Confirmed the scorers are running at the right sample rates |
# MAGIC | 7 | Drove tier-1 + tier-2 traffic at the agent in-process |
# MAGIC | 8 | Found the scorer assessments on the resulting traces via SQL |
# MAGIC | 9 | Paused the scorers so they don't keep running |
# MAGIC
# MAGIC The same `register_monitoring_scorers(monitoring_config=...)` call runs
# MAGIC verbatim against a deployed Model Serving endpoint or a deployed
# MAGIC Databricks App -- the only thing that changes is *which* experiment_id
# MAGIC you point at. The YAML stays the same.
# MAGIC
# MAGIC ## A natural next lab
# MAGIC
# MAGIC `app.trace_location` can route traces to a Unity Catalog Delta table
# MAGIC (OTEL spans), at which point a Lakehouse Monitoring dashboard on that
# MAGIC table closes the loop: scorers run continuously, assessments land in
# MAGIC UC, and dashboards alert on regressions.
