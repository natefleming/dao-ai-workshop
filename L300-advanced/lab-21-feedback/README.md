# Lab 21 -- User Feedback on Agent Responses

**Level:** L300

## Goal

Capture thumbs-up / thumbs-down feedback against a dao-ai multi-agent response and
verify that the feedback attaches to the **outer** root trace (the one whose
children include every sub-agent hop), not to a sub-agent leg.

## What you'll do

1. Build a small two-agent supervisor (`tier1_support` + `tier2_engineer`).
2. Invoke `agent.apredict(...)` and read `trace_id` out of
   `response.custom_outputs["trace_id"]`.
3. Call `dao_ai.evaluation.log_user_feedback(trace_id=..., value="up"/"down", ...)`.
4. Verify with `mlflow.get_trace` that the trace_id IS the outer
   multi-agent root.
5. Query feedback rows with `mlflow.search_traces` + a single Spark SQL
   `LATERAL VIEW EXPLODE(assessments)` query.

## Why the dao-ai pattern matters

In an in-process or remote multi-agent flow there are typically many
spans per user turn. Reading the trace_id from MLflow global state in
the caller is unsafe:

| Anti-pattern | Failure mode |
|---|---|
| `mlflow.get_last_active_trace_id()` | Races under concurrency -- desyncs from the trace this call produced |
| `mlflow.get_current_active_span().trace_id` | Returns `None` once the agent function returns; `.trace_id` raises `AttributeError` |
| `mlflow.log_assessment(...)` / legacy `Assessment(...)` | MLflow 2.x preview API, deprecated in MLflow 3 |

dao-ai 0.1.87+ exposes the outer trace_id on `custom_outputs` and provides
`log_user_feedback` which wraps `mlflow.log_feedback` with cross-process
trace-queryability polling so the helper works the same on in-process
invocation, deployed Model Serving endpoints, and Databricks Apps.

## Files

| File | Purpose |
|---|---|
| `notebook.py` | The lab notebook. |
| `feedback_agent.yaml` | Minimal two-agent supervisor config (saas_helpdesk theme). |
| `pyproject.toml` | dao-ai version pin. |

## Prerequisites

- Lab 9 completed (supervisor / multi-agent orchestration).
- Workspace access to MLflow tracing (any Databricks workspace with
  MLflow 3 enabled -- all current FE workspaces qualify).

## Run it

Open `notebook.py` in Databricks and Run All. The notebook handles
parameter substitution from your username automatically. Default LLM
endpoints are `databricks-claude-sonnet-4-5` and
`databricks-claude-haiku-4-5`; override via the notebook widgets if
those aren't available in your workspace.
