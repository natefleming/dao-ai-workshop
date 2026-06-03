# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 24 -- UC OTEL Trace Tables via `app.trace_location`
# MAGIC
# MAGIC **Level:** L300
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Declare `app.trace_location` on a dao-ai agent so MLflow writes
# MAGIC   traces to Unity Catalog OTEL Delta tables.
# MAGIC - Call `set_experiment_trace_location` + `set_destination` from the
# MAGIC   notebook (dao-ai's runtime does this for Model Serving / Apps, but
# MAGIC   in-process notebooks have to do it themselves).
# MAGIC - Verify the three OTEL tables (`..._otel_spans`, `..._otel_logs`,
# MAGIC   `..._otel_metrics`) are created in the configured UC schema.
# MAGIC - Drive traffic and watch trace spans land in
# MAGIC   `${catalog}.${schema}.mlflow_experiment_trace_otel_spans`.
# MAGIC - Use Spark SQL to slice the spans table by user / sub-agent /
# MAGIC   trace_id -- the same query path you'd use for a Lakehouse
# MAGIC   Monitoring dashboard.
# MAGIC
# MAGIC ## Why this matters
# MAGIC
# MAGIC Experiment-resident traces (Lab 21/22/23) are great for development.
# MAGIC For anything *durable* -- joining traces to other UC tables (user
# MAGIC profile, feedback, A/B cohort), building Lakehouse Monitoring
# MAGIC dashboards, retaining traces beyond MLflow's default lifecycle --
# MAGIC traces need to live in UC. `app.trace_location` is one YAML block
# MAGIC that gets you there.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 -- Install dependencies

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.88"
# MAGIC %restart_python

# COMMAND ----------

from importlib.metadata import version

print(f"dao-ai={version('dao-ai')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 -- Configure parameters
# MAGIC
# MAGIC The `warehouse_id` widget is required for this lab -- the OTEL trace
# MAGIC writer uses the warehouse to provision the Delta tables and to query
# MAGIC them during writes. Use a warehouse you have CAN_USE on; the
# MAGIC `Serverless Starter Warehouse` is a fine default in most FE workspaces.

# COMMAND ----------

import asyncio
import os
import re

import nest_asyncio

nest_asyncio.apply()
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
dbutils.widgets.text("warehouse_id", "", "SQL warehouse ID (required)")
dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-4-5", "Default LLM")
dbutils.widgets.text("fast_llm_endpoint", "databricks-claude-haiku-4-5", "Fast LLM (tier-1)")

warehouse_id: str = dbutils.widgets.get("warehouse_id").strip()
if not warehouse_id:
    raise ValueError(
        "warehouse_id is required. Set the widget to a SQL warehouse ID "
        "that you have CAN_USE on."
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

experiment = mlflow.set_experiment(f"/Users/{USER}/Lab24-trace-location")
experiment_id: str = experiment.experiment_id
print(f"experiment: {experiment.name} ({experiment_id})")

config: AppConfig = AppConfig.from_file("otel_agent.yaml", params=params)

for schema in config.schemas.values():
    schema.create()

agent = config.as_responses_agent()
print(f"App: {config.app.name}")
print(f"Agents: {[a.name for a in config.app.agents]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- Link the experiment to the UC trace location
# MAGIC
# MAGIC dao-ai's Model Serving and Databricks Apps deploy paths call
# MAGIC `set_experiment_trace_location` automatically at startup
# MAGIC (`dao_ai/providers/databricks.py:833-865` and `apps/handlers.py:67-93`).
# MAGIC In-process notebooks don't go through either path, so we make the
# MAGIC call ourselves -- once. The link is idempotent: re-running this cell
# MAGIC is a no-op once the experiment is already linked.

# COMMAND ----------

from mlflow.entities import UCSchemaLocation
from mlflow.tracing.enablement import set_experiment_trace_location

loc = config.app.trace_location
print(f"trace_location: {loc.catalog_name}.{loc.schema_name} via warehouse {loc.warehouse_id}")

try:
    set_experiment_trace_location(
        location=UCSchemaLocation(
            catalog_name=loc.catalog_name,
            schema_name=loc.schema_name,
        ),
        experiment_id=experiment_id,
        sql_warehouse_id=loc.warehouse_id,
    )
    print("Linked experiment to UC trace location")
except Exception as e:
    msg = str(e)
    if "already contains traces" in msg or "already linked" in msg.lower():
        print("Experiment was already linked, continuing")
    else:
        raise

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 -- Verify the three OTEL Delta tables exist
# MAGIC
# MAGIC `TraceLocationModel.OTEL_TABLE_SUFFIXES` enumerates the three tables
# MAGIC MLflow creates: `mlflow_experiment_trace_otel_spans`,
# MAGIC `mlflow_experiment_trace_otel_logs`,
# MAGIC `mlflow_experiment_trace_otel_metrics`.

# COMMAND ----------

from dao_ai.config import TraceLocationModel

schema_prefix: str = f"{loc.catalog_name}.{loc.schema_name}"
print(f"Checking {schema_prefix} for OTEL tables...")
for suffix in TraceLocationModel.OTEL_TABLE_SUFFIXES:
    fqn = f"{schema_prefix}.{suffix}"
    exists = spark.catalog.tableExists(fqn)
    print(f"  {fqn}: {'OK' if exists else 'MISSING'}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 -- Route the in-process tracer to UC
# MAGIC
# MAGIC `set_experiment_trace_location` (Step 4) registers the link, but the
# MAGIC current Python process's MLflow tracer also needs to be told to write
# MAGIC spans to UC instead of the default experiment store. `set_destination`
# MAGIC handles that. Apps and Model Serving call this inside
# MAGIC `dao_ai/apps/handlers.py:67-93`; the notebook does it directly.

# COMMAND ----------

mlflow.tracing.set_destination(
    destination=UCSchemaLocation(
        catalog_name=loc.catalog_name,
        schema_name=loc.schema_name,
    )
)
print("In-process tracer now routes to UC OTEL tables")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 -- Drive traffic
# MAGIC
# MAGIC Six requests -- three tier-1, three tier-2 -- to get a useful mix of
# MAGIC root + sub-agent spans into the OTEL spans table.

# COMMAND ----------

import time
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

print("\nGiving the OTEL writer ~15s to flush spans to UC...")
time.sleep(15)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 8 -- Query the OTEL spans table via Spark SQL
# MAGIC
# MAGIC The spans table is the durable record of every step in every trace.
# MAGIC Each row is one span; nested spans are linked via `parent_span_id`.

# COMMAND ----------

spans_table: str = f"{schema_prefix}.mlflow_experiment_trace_otel_spans"
print(f"Querying {spans_table}...")
spark.sql(f"SELECT COUNT(*) AS span_count FROM {spans_table}").display()

# COMMAND ----------

# MAGIC %md
# MAGIC Span-count per trace (one trace = one user turn = many spans).

# COMMAND ----------

spark.sql(f"""
    SELECT trace_id, COUNT(*) AS spans, MIN(start_time_unix_nano) AS first_span_ns
    FROM {schema_prefix}.mlflow_experiment_trace_otel_spans
    WHERE trace_id IS NOT NULL
    GROUP BY trace_id
    ORDER BY first_span_ns DESC
    LIMIT 20
""").display()

# COMMAND ----------

# MAGIC %md
# MAGIC The span types for one specific trace (run after the cell above so
# MAGIC you can pick a trace_id with > 1 span):

# COMMAND ----------

if trace_ids:
    sample_trace = trace_ids[-1]  # most recent, most likely to be present
    print(f"Inspecting spans for trace_id={sample_trace}")
    spark.sql(f"""
        SELECT name, kind, status
        FROM {schema_prefix}.mlflow_experiment_trace_otel_spans
        WHERE trace_id = '{sample_trace}'
        ORDER BY start_time_unix_nano ASC
    """).display()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 9 -- What you just did
# MAGIC
# MAGIC | Step | Action |
# MAGIC |---|---|
# MAGIC | 4 | Linked the experiment to a UC schema via `set_experiment_trace_location` |
# MAGIC | 5 | Verified MLflow auto-created the three OTEL Delta tables |
# MAGIC | 6 | Pointed this notebook's tracer at the UC destination via `set_destination` |
# MAGIC | 7 | Drove six requests at the agent; traces flushed to the UC spans table |
# MAGIC | 8 | Queried the spans table directly -- one trace per user turn, many spans per trace |
# MAGIC
# MAGIC The spans table is what unlocks the productionised story: build a
# MAGIC Lakehouse Monitoring dashboard on it for trace-volume / latency /
# MAGIC error-rate over time, JOIN it to `mlflow.search_traces` assessments
# MAGIC (Lab 21 + Lab 23) to slice quality by user or cohort, or retain
# MAGIC traces past MLflow's default lifecycle simply by reading the Delta
# MAGIC table directly. For a deployed app, dao-ai does all of Steps 4 + 6
# MAGIC automatically -- you just write the YAML.
