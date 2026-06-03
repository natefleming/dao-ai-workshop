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
| `monitoring_agent.yaml` | Same two-tier supervisor as Lab 21/22 + the `app.monitoring` block. |
| `pyproject.toml` | dao-ai version pin (`>=0.1.90`). |

## Prerequisites

- Lab 22 completed (you've already seen `Guidelines` scorers and
  `mlflow.genai.evaluate` against offline datasets).
- A SQL warehouse ID (optional but recommended) for the `warehouse_id`
  widget if you eventually route traces to UC OTEL tables. Without it the
  lab still works against experiment-resident traces.

## Run it

Open `notebook.py` in Databricks and Run All. The notebook handles per-student
naming. Step 7 sleeps 20s to give the async monitoring scorers time to attach
assessments to the freshly-generated traces before Step 8 queries them; under
load you may need to lengthen this delay or re-run the SQL cell after a moment.

## Next

`app.trace_location` routes traces to a Unity Catalog Delta table (OTEL
spans), at which point a Lakehouse Monitoring dashboard on that table closes
the loop: scorers run continuously, assessments land in UC, and dashboards
alert on regressions. That's the natural Lab 24.
