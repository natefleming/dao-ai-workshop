# Lab 24 -- UC OTEL Trace Tables via `app.trace_location`

**Level:** L300

## Goal

Set `app.trace_location` on the same `saas_helpdesk` supervisor and route
traces to Unity Catalog OTEL Delta tables. Verify the three tables get
created, drive traffic, and query the spans table with Spark SQL.

## What you'll do

1. Declare `app.trace_location` in YAML with a schema reference + warehouse.
2. From the notebook, call `set_experiment_trace_location` to link the
   experiment to the UC schema. (dao-ai's Model Serving and Apps deploy
   paths call this automatically; in-process notebooks call it directly.)
3. Verify MLflow auto-created the three OTEL tables:
   - `<catalog>.<schema>.mlflow_experiment_trace_otel_spans`
   - `<catalog>.<schema>.mlflow_experiment_trace_otel_logs`
   - `<catalog>.<schema>.mlflow_experiment_trace_otel_metrics`
4. Call `mlflow.tracing.set_destination` so this notebook's tracer routes
   new spans to UC. (Apps and Model Serving call this in
   `dao_ai/apps/handlers.py:67-93`.)
5. Drive six tier-1 / tier-2 prompts at the agent.
6. Query `..._otel_spans` directly with Spark SQL -- one row per span,
   `trace_id` joins them back to a single user turn.

## Why the dao-ai pattern matters

| Where it lives | What it controls |
|---|---|
| `app.trace_location.schema` | The UC schema where OTEL tables are created |
| `app.trace_location.warehouse` | SQL warehouse the OTEL writer uses to provision + write |
| `TraceLocationModel.OTEL_TABLE_SUFFIXES` | The three table names MLflow creates |
| `TraceLocationModel.as_resources()` | `DatabricksTable` resource entries so Model Serving auto-grants SELECT on the OTEL tables |

For deployments, dao-ai calls `set_experiment_trace_location` + grants
`MODIFY` + `SELECT` on the OTEL tables to the agent's SP automatically
(`dao_ai/providers/databricks.py:889-958`). For in-process notebook work
you make the same two MLflow calls yourself once -- the rest of the lab
(driving traffic, querying spans) is unchanged.

## Files

| File | Purpose |
|---|---|
| `notebook.py` | The lab notebook. |
| `otel_agent.yaml` | Same two-tier supervisor as Lab 21/22/23 plus an `app.trace_location` block and an `app.monitoring` block. |
| `pyproject.toml` | dao-ai version pin (`>=0.1.88`). |

## Prerequisites

- Lab 23 completed (you've seen `app.monitoring`; this lab layers
  `app.trace_location` on top).
- A UC catalog/schema you can write to (defaults to
  `main.dao_ai_workshop`). The lab self-provisions the three OTEL tables
  on first run.
- **A SQL warehouse ID is required.** The `warehouse_id` widget feeds
  `app.trace_location.warehouse` -- without it the OTEL writer can't
  provision the tables. The `Serverless Starter Warehouse` is fine in
  most FE workspaces.

## Run it

Open `notebook.py` in Databricks and Run All. The notebook will fail
fast (a `ValueError`) if you don't fill the `warehouse_id` widget.

## Next

This is the durable foundation for production monitoring. Once the
spans live in UC, a Lakehouse Monitoring dashboard on
`..._otel_spans` (latency / error_rate / volume rollups) closes the
loop on what Lab 23 started.
