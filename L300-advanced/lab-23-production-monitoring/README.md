# Lab 23 -- Production Monitoring with Registered Scorers

**Level:** L300

## Goal

Wire up the MLflow 3 scorer lifecycle so a chosen set of judges runs
**continuously** against new traces from a dao-ai agent, with sample rates
controlled from YAML. Verify the assessments land on the right traces and
inspect them with a single Spark SQL query.

## What you'll do

1. Load a dao-ai agent whose YAML carries an `app.monitoring` block.
2. Inspect the parsed `MonitoringModel` so you can see the relationship
   between YAML and Python.
3. Call `dao_ai.evaluation.register_monitoring_scorers` -- this is the
   idempotent helper that converges the MLflow scorer lifecycle to the
   YAML-declared state on every deploy.
4. Drive a small batch of tier-1 + tier-2 requests at the agent in-process.
5. Wait briefly (monitoring runs out-of-band), then query the traces and
   render the assessment value + rationale per scorer with a single
   `LATERAL VIEW EXPLODE(assessments)` SQL cell.
6. Stop the scorers with `stop_monitoring_scorers()` so they don't keep
   running on the shared workspace.

## Why the dao-ai pattern matters

dao-ai turns "what should we monitor in production" into a YAML block:

```yaml
app:
  monitoring:
    sample_rate: 1.0
    scorers:
      - safety
      - relevance_to_query
      - tool_call_efficiency
    guidelines_sample_rate: 0.5
    guidelines:
      - name: routing_quality
        guidelines:
          - ...
      - name: hallucination_guard
        guidelines:
          - ...
```

`register_monitoring_scorers` reads that block, builds the right scorer
instances, registers each against the active MLflow experiment, and starts
(or updates) them at the declared sample rate. The same call works against
in-process agents, deployed Model Serving endpoints, and deployed Databricks
Apps -- the only thing that changes between them is *which* experiment_id
you point at.

## Files

| File | Purpose |
|---|---|
| `notebook.py` | The lab notebook -- inspect, register, drive traffic, verify, cleanup. |
| `monitoring_agent.yaml` | Same two-tier supervisor as Lab 21/22 + the `app.monitoring` block + an `app.trace_location` block (required since this lab deploys to Apps — see "Prerequisites" below). |
| `pyproject.toml` | dao-ai version pin (`>=0.1.92`). |

## Prerequisites

- Lab 22 completed (you've already seen `Guidelines` scorers and
  `mlflow.genai.evaluate` against offline datasets).
- **A SQL warehouse ID is required** for the `warehouse_id` widget — this
  lab deploys to Databricks Apps, and Apps containers can't reach the
  default MLflow trace export host, so traces would be silently dropped
  without `app.trace_location` routing them through a warehouse to UC OTEL
  Delta tables. Lab 24 walks through this pattern in depth.
- After the first deploy, grant the App SP schema-level privileges on the
  trace schema so MLflow can create + write the OTEL tables (one-time):
  ```sql
  GRANT USE_CATALOG ON CATALOG <catalog> TO `<app-sp-client-id>`;
  GRANT USE_SCHEMA, CREATE_TABLE, MODIFY, SELECT
    ON SCHEMA <catalog>.<schema>
    TO `<app-sp-client-id>`;
  ```
- **The "Managed Evaluations" feature must be enabled on your workspace**
  for the backend `Trace Metrics Computation Job` to actually run the
  registered scorers against incoming traces. `register_monitoring_scorers`
  succeeds either way (registration is purely metadata), and you can verify
  the scorers in `mlflow.genai.scorers.list_scorers()` -- but no
  `assessments` will appear on traces until that job runs successfully.
  Most current Field Engineering workspaces have Managed Evals enabled;
  a workspace without it surfaces a `403 PERMISSION_DENIED: This feature
  has not been enabled for this workspace.` in that job's logs and the
  lab's Step 8 SQL cell will return zero rows.

## Run it

Open `notebook.py` in Databricks and Run All. The notebook handles per-student
naming. Step 7 sleeps 20s to give the async monitoring scorers time to attach
assessments to the freshly-generated traces before Step 8 queries them; under
load you may need to lengthen this delay or re-run the SQL cell after a moment.

## Next

This lab already routes traces to UC via `app.trace_location`. Lab 24 zooms
in on that block: schema choices, the optional `table_prefix`, querying
`..._otel_spans` directly with Spark SQL, and the in-process notebook flow
that mirrors what dao-ai does automatically inside Model Serving / Apps
deploys. The natural production follow-on is a Lakehouse Monitoring
dashboard on `..._otel_spans` — scorers run continuously, assessments land
in UC, and dashboards alert on regressions.
