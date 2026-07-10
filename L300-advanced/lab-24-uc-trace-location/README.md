# Lab 24 -- UC OTEL Trace Tables via `app.trace_location`

**Level:** L300

## Goal

Set `app.trace_location` on the same `saas_helpdesk` supervisor and route
traces to Unity Catalog OTEL Delta tables. Verify the three tables get
created, drive traffic, and query the spans table with Spark SQL.

## What you'll do

1. Declare `app.trace_location` in YAML with a schema reference + warehouse.
2. From the notebook, call `mlflow.set_experiment(experiment_id=..., trace_location=UnityCatalog(...))`
   to link the experiment to the UC schema. (dao-ai's Model Serving and
   Apps deploy paths do this automatically inside
   `_link_experiment_trace_location`; in-process notebooks call it
   directly.) This is the post-MLflow-3.11 blessed API — it replaces the
   older `set_experiment_trace_location` + `set_destination` +
   `UCSchemaLocation` trio, both of which emit deprecation warnings.
3. Verify MLflow auto-created the three OTEL tables (named with
   `<prefix>_otel_{spans,logs,metrics}`, where `<prefix>` is
   `app.trace_location.table_prefix` if set, otherwise the experiment_id):
   - `<catalog>.<schema>.<prefix>_otel_spans`
   - `<catalog>.<schema>.<prefix>_otel_logs`
   - `<catalog>.<schema>.<prefix>_otel_metrics`
4. Drive six tier-1 / tier-2 prompts at the agent.
5. Query `..._otel_spans` directly with Spark SQL -- one row per span,
   `trace_id` joins them back to a single user turn.

## Why the dao-ai pattern matters

| Where it lives | What it controls |
|---|---|
| `app.trace_location.schema` | The UC schema where OTEL tables are created |
| `app.trace_location.warehouse` | SQL warehouse the OTEL writer uses to provision + write |
| `app.trace_location.table_prefix` (optional) | Stable name prefix when multiple agents share a schema; defaults to the experiment_id |
| `TraceLocationModel.as_resources()` | dao-ai intentionally does NOT declare the OTEL tables here — they don't exist at deploy time, so concrete table names in the auth_policy would cause `agents.deploy` to abort with `TABLE_DOES_NOT_EXIST`. Schema-level grants below cover the runtime SP instead. |

For deployments, dao-ai calls
`mlflow.set_experiment(trace_location=UnityCatalog(...))` automatically
(see `dao_ai/providers/databricks.py::_link_experiment_trace_location`).
The runtime identity (Model Serving SP or Apps SP) needs schema-level
grants so MLflow can create + write the OTEL tables at first export.

## Post-deploy grants

The runtime App SP is **not** in any group by default, so it inherits
nothing. After the first deploy, grant the SP these privileges on the
trace schema (one-time):

```sql
GRANT USE_CATALOG ON CATALOG <catalog> TO `<app-sp-client-id>`;
GRANT USE_SCHEMA, CREATE_TABLE, MODIFY, SELECT
  ON SCHEMA <catalog>.<schema>
  TO `<app-sp-client-id>`;
```

Find the App SP client id in the app's resource list (or via
`databricks apps get <app-name>`). For Model Serving, grant the same on
the Mosaic AI runtime SP for that endpoint.

For in-process notebook work you make the modern `mlflow.set_experiment`
call yourself once -- the rest of the lab (driving traffic, querying
spans) is unchanged.

## Files

| File | Purpose |
|---|---|
| `notebook.py` | The lab notebook. |
| `otel_agent.yaml` | Same two-tier supervisor as Lab 21/22/23 plus an `app.trace_location` block and an `app.monitoring` block. Runs in-process. |
| `otel_agent_model_serving.yaml` | Same agents, deployed to Model Serving. Adds `registered_model` + `service_principal` blocks; distinct `table_prefix: lab24_ms_traces`. |
| `pyproject.toml` | dao-ai version pin (`>=0.1.92`). |

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

## Model Serving variant

The tail of the notebook (Step 11) redeploys the same two-tier
supervisor to Databricks Model Serving using
`otel_agent_model_serving.yaml`. Key differences from the Apps /
in-process demo:

- **No manual GRANT SQL.** Because `app.service_principal` is declared,
  dao-ai auto-grants CAN_EDIT on the experiment and USE_SCHEMA/MODIFY
  on the trace UC schema at deploy time (see
  `_grant_experiment_permissions_to_principal` +
  `_grant_uc_trace_table_permissions_to_principal` in
  `dao_ai/providers/databricks.py`). Contrast the "Post-deploy grants"
  section above, which applies to the Apps path.
- **Container no longer touches MLflow config.** The recent `d035c13`
  fix removed `mlflow.set_experiment` from the MS entrypoint. Trace
  routing is driven entirely by env vars (`MLFLOW_EXPERIMENT_ID`,
  `MLFLOW_TRACING_DESTINATION`, `MLFLOW_TRACING_SQL_WAREHOUSE_ID`) set
  on the endpoint config by `agents.deploy()`. The experiment link
  happens on the notebook side inside `_link_experiment_trace_location`
  before deploy.
- **Distinct `table_prefix`.** The MS variant writes to
  `<schema>.lab24_ms_traces_otel_spans`; the Apps/in-process demo
  writes to `<schema>.lab24_traces_otel_spans`. Same schema, distinct
  tables -- easy to verify each path independently.

### Prereq

The shared workshop service principal must exist. Run
`setup/create_service_principal.py` once per workspace before Step 11.
This provisions the `dao-ai-workshop-sp` SP and populates
`dao_ai_workshop`/`DAO_AI_SP_CLIENT_ID` +
`DAO_AI_SP_CLIENT_SECRET`. The YAML pulls those secrets via the same
composite-variable pattern lab-07 / lab-15 use for Lakebase.

## Next

This is the durable foundation for production monitoring. Once the
spans live in UC, a Lakehouse Monitoring dashboard on
`..._otel_spans` (latency / error_rate / volume rollups) closes the
loop on what Lab 23 started.
