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
# MAGIC - Call `mlflow.set_experiment(experiment_id=..., trace_location=UnityCatalog(...))`
# MAGIC   from the notebook (dao-ai's runtime does this automatically for
# MAGIC   Model Serving / Apps, but in-process notebooks have to do it
# MAGIC   themselves).
# MAGIC - Verify the three OTEL tables (`..._otel_spans`, `..._otel_logs`,
# MAGIC   `..._otel_metrics`) are created in the configured UC schema.
# MAGIC - Drive traffic and watch trace spans land in
# MAGIC   `${catalog}.${schema}.<prefix>_otel_spans` (where `<prefix>` is
# MAGIC   `app.trace_location.table_prefix` if set, otherwise the
# MAGIC   experiment_id).
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

# MAGIC %pip install "dao-ai>=0.1.101"
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
from dao_ai.logging import suppress_autolog_context_warnings

# Parity with dao_ai/apps/handlers.py:100 + apps/model_serving.py:59 —
# the deployed-App runtime does exactly these two calls automatically.
# In-notebook usage must do them explicitly; without ``run_tracer_inline=True``
# LangChain callbacks fire on thread-pool workers and MLflow's active-span
# ContextVar is lost across threads, so OTEL spans never finalize and
# ``<prefix>_otel_spans`` never gets materialized by the exporter.
mlflow.langchain.autolog(run_tracer_inline=True)
suppress_autolog_context_warnings()

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
# MAGIC `mlflow.set_experiment(experiment_id=..., trace_location=UnityCatalog(...))`
# MAGIC automatically at startup
# MAGIC (see `dao_ai/providers/databricks.py::_link_experiment_trace_location`
# MAGIC and `dao_ai/apps/handlers.py`). In-process notebooks don't go through
# MAGIC either path, so we make the call ourselves -- once. This is the
# MAGIC post-MLflow-3.11 blessed API; the older
# MAGIC `set_experiment_trace_location` + `set_destination` + `UCSchemaLocation`
# MAGIC trio emits deprecation warnings on every call. The link is
# MAGIC idempotent: re-running this cell is a no-op once the experiment is
# MAGIC already linked.

# COMMAND ----------

from mlflow.entities import UnityCatalog

loc = config.app.trace_location
print(f"trace_location: {loc.catalog_name}.{loc.schema_name} via warehouse {loc.warehouse_id}")

trace_kwargs: dict = {"catalog_name": loc.catalog_name, "schema_name": loc.schema_name}
if loc.resolved_table_prefix:
    trace_kwargs["table_prefix"] = loc.resolved_table_prefix

try:
    mlflow.set_experiment(
        experiment_id=experiment_id,
        trace_location=UnityCatalog(**trace_kwargs),
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
# MAGIC MLflow creates three OTEL Delta tables in the configured UC schema,
# MAGIC named `<prefix>_otel_spans`, `<prefix>_otel_logs`, and
# MAGIC `<prefix>_otel_metrics`. The prefix is `app.trace_location.table_prefix`
# MAGIC when set, otherwise the experiment_id. Tables are created lazily on
# MAGIC first trace export, so we'll re-check this cell after Step 7 drives
# MAGIC traffic.

# COMMAND ----------

table_prefix = loc.resolved_table_prefix or experiment_id
schema_fqn: str = f"{loc.catalog_name}.{loc.schema_name}"
print(f"Checking {schema_fqn} for OTEL tables (prefix={table_prefix})...")
for suffix in ("otel_spans", "otel_logs", "otel_metrics"):
    fqn = f"{schema_fqn}.{table_prefix}_{suffix}"
    exists = spark.catalog.tableExists(fqn)
    print(f"  {fqn}: {'OK' if exists else 'MISSING (created on first trace export)'}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 -- (Not needed) -- modern API combines link + destination
# MAGIC
# MAGIC The older `set_experiment_trace_location` + `mlflow.tracing.set_destination`
# MAGIC two-step dance has been replaced by a single
# MAGIC `mlflow.set_experiment(experiment_id=..., trace_location=UnityCatalog(...))`
# MAGIC call. The link in Step 4 also activates the in-process tracer for the
# MAGIC linked experiment. No additional `set_destination` is required.

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

print("\nWaiting for the OTEL writer to flush spans to UC...")
# The OTEL exporter creates <schema>.<prefix>_otel_spans lazily on the
# first flush. A fixed sleep is fragile because first-time table
# creation on a cold OTEL pipeline can take several minutes. Force any
# buffered MLflow trace exports out first, then poll for the table.
try:
    mlflow.flush_trace_async_logging()
except Exception:
    pass  # older mlflow versions or non-async paths -- ignore

_spans_fqn = f"{schema_fqn}.{table_prefix}_otel_spans"
_deadline = time.time() + 600  # 10 min hard cap
while time.time() < _deadline:
    try:
        # Fully qualified reference forces table resolution; if the table
        # doesn't exist yet, this raises TABLE_OR_VIEW_NOT_FOUND. If it
        # does exist but is empty, the query returns 0 rows immediately.
        spark.sql(f"SELECT 1 FROM {_spans_fqn} LIMIT 1").collect()
        print(f"OTEL table ready: {_spans_fqn}")
        break
    except Exception as _e:
        time.sleep(10)
else:
    print(f"Timed out waiting for {_spans_fqn} to be created by the OTEL exporter.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 8 -- Query the OTEL spans table via Spark SQL
# MAGIC
# MAGIC The spans table is the durable record of every step in every trace.
# MAGIC Each row is one span; nested spans are linked via `parent_span_id`.

# COMMAND ----------

spans_table: str = f"{schema_fqn}.{table_prefix}_otel_spans"
print(f"Querying {spans_table}...")

spark.sql(f"SELECT COUNT(*) AS span_count FROM {spans_table}").display()

# COMMAND ----------

# MAGIC %md
# MAGIC Span-count per trace (one trace = one user turn = many spans).

# COMMAND ----------

spark.sql(f"""
    SELECT trace_id, COUNT(*) AS spans, MIN(start_time_unix_nano) AS first_span_ns
    FROM {schema_fqn}.{table_prefix}_otel_spans
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
        FROM {schema_fqn}.{table_prefix}_otel_spans
        WHERE trace_id = '{sample_trace}'
        ORDER BY start_time_unix_nano ASC
    """).display()

# COMMAND ----------

# MAGIC %md
# MAGIC ### One row per trace (the canonical "select traces" query)
# MAGIC
# MAGIC The spans table is one row per span. To get the shape a dashboard
# MAGIC wants -- one row per trace, with duration / root span / error
# MAGIC counts rolled up -- group by `trace_id`. This is the query you'd
# MAGIC point Lakehouse Monitoring at to chart trace volume, p95 latency,
# MAGIC or error rate over time.

# COMMAND ----------

spark.sql(f"""
    SELECT
      trace_id,
      MIN_BY(name, start_time_unix_nano)                                AS root_span_name,
      MIN_BY(kind, start_time_unix_nano)                                AS root_span_kind,
      COUNT(*)                                                           AS span_count,
      (MAX(end_time_unix_nano) - MIN(start_time_unix_nano)) / 1e6        AS duration_ms,
      SUM(CASE WHEN status.code = 'STATUS_CODE_ERROR' THEN 1 ELSE 0 END) AS error_spans,
      MIN(start_time_unix_nano)                                          AS start_ns
    FROM {schema_fqn}.{table_prefix}_otel_spans
    WHERE trace_id IS NOT NULL
    GROUP BY trace_id
    ORDER BY start_ns DESC
    LIMIT 20
""").display()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 9 -- The companion tables: `otel_logs` and `otel_metrics`
# MAGIC
# MAGIC `otel_spans` is the table you'll touch most often. `otel_logs` and
# MAGIC `otel_metrics` are the OpenTelemetry siblings:
# MAGIC
# MAGIC | Table | Holds | Populated when |
# MAGIC |---|---|---|
# MAGIC | `..._otel_spans` | One row per span -- agent steps, tool calls, sub-agent handoffs | Always, for every traced call |
# MAGIC | `..._otel_logs` | Structured log records emitted via the OTEL logs API or `@mlflow.trace` events | When the agent or its tools emit log events |
# MAGIC | `..._otel_metrics` | OTEL metric samples (counters / histograms) | Only if your code emits OTEL metrics; dao-ai's default agent runtime does not, so this is usually empty |
# MAGIC
# MAGIC Out-of-the-box dao-ai produces lots of spans and a handful of logs;
# MAGIC `otel_metrics` stays empty in this lab. That's expected.

# COMMAND ----------

# OTEL logs sibling -- a few rows per traced turn.
print(f"Row counts across all three OTEL tables in {schema_fqn} (prefix={table_prefix}):")
for suffix in ("otel_spans", "otel_logs", "otel_metrics"):
    fqn = f"{schema_fqn}.{table_prefix}_{suffix}"
    row_count = spark.sql(f"SELECT COUNT(*) FROM {fqn}").first()[0]
    print(f"  {table_prefix}_{suffix:14s} {row_count} rows")

# COMMAND ----------

# Sample the logs table (only meaningful if rows > 0).
spark.sql(f"""
    SELECT trace_id, severity_text, body, observed_time_unix_nano
    FROM {schema_fqn}.{table_prefix}_otel_logs
    ORDER BY observed_time_unix_nano DESC
    LIMIT 10
""").display()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 10 -- What you just did
# MAGIC
# MAGIC | Step | Action |
# MAGIC |---|---|
# MAGIC | 4 | Linked the experiment to a UC schema via `mlflow.set_experiment(trace_location=UnityCatalog(...))` |
# MAGIC | 5 | Verified MLflow auto-created the three OTEL Delta tables |
# MAGIC | 6 | (Skipped — the modern API combines link + destination into one call.) |
# MAGIC | 7 | Drove six requests at the agent; traces flushed to the UC spans table |
# MAGIC | 8 | Queried the spans table directly -- counts, span-per-trace breakdown, per-trace inspection, and the canonical "one row per trace" rollup |
# MAGIC | 9 | Surveyed the companion tables (`otel_logs`, `otel_metrics`) |
# MAGIC
# MAGIC The spans table is what unlocks the productionised story: build a
# MAGIC Lakehouse Monitoring dashboard on the one-row-per-trace query for
# MAGIC trace-volume / latency / error-rate over time, JOIN it to
# MAGIC `mlflow.search_traces` assessments (Lab 21 + Lab 23) to slice
# MAGIC quality by user or cohort, or retain traces past MLflow's default
# MAGIC lifecycle simply by reading the Delta table directly. For a
# MAGIC deployed app, dao-ai calls Step 4 automatically inside
# MAGIC `_link_experiment_trace_location` -- you just write the YAML.
