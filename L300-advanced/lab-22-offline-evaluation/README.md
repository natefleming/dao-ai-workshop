# Lab 22 -- Offline Evaluation with Judges and Datasets

**Level:** L300

## Goal

Run `mlflow.genai.evaluate()` against the same two-tier SaaS support supervisor
from Lab 21 (`tier1_support` + `tier2_engineer`) using four progressively
richer evaluation patterns -- config-defined datasets, externally-sourced
datasets, custom scorers, and per-row guidelines.

## What you'll do

1. **Scenario A -- Config-defined inline dataset.** Use
   `EvaluationDatasetModel` declared in YAML under
   `optimizations.training_datasets`, call
   `dao_ai.evaluation.build_scorers(config.evaluation)`, run
   `mlflow.genai.evaluate(...)`.
2. **Scenario B -- UC Delta table -> managed MLflow dataset.** Write rows to
   `${catalog}.${schema}.lab22_eval_external`, register it as an MLflow
   dataset via `mlflow.genai.datasets.create_dataset` + `.merge_records`, and
   evaluate the same agent against it.
3. **Scenario C -- Custom `@scorer`.** Author a custom scorer returning an
   `mlflow.entities.Feedback` (e.g., "must include a concrete action verb")
   and stack it on top of the built-in scorers.
4. **Scenario D -- Per-row guidelines via `ExpectationsGuidelines`.** Build
   an in-memory dataset where each row carries its own
   `expectations.guidelines`, then evaluate with
   `mlflow.genai.scorers.ExpectationsGuidelines()`.

## Why the dao-ai pattern matters

| Surface | Provided by |
|---|---|
| `EvaluationModel` (judge LLM, payload table, guidelines) | dao-ai config |
| `EvaluationDatasetModel` -> `mlflow.genai.datasets.EvaluationDataset` | dao-ai config |
| `build_scorers(config.evaluation)` -- assembles Safety / Completeness / RelevanceToQuery / ToolCallEfficiency + Guidelines | `dao_ai.evaluation` |
| Managed datasets sourced from UC tables | `mlflow.genai.datasets.create_dataset` + `.merge_records` (raw MLflow) |
| Custom scorers, per-row guidelines, `Correctness` against `expected_facts` | `mlflow.genai.scorers.*` (raw MLflow) |

dao-ai gives you the config-level surface; raw MLflow fills in everything that
isn't worth modeling in YAML. This lab shows both sides side-by-side.

## Files

| File | Purpose |
|---|---|
| `notebook.py` | The lab notebook -- four scenarios end-to-end. |
| `evaluation_agent.yaml` | Same two-tier supervisor as Lab 21 plus the `evaluation:` block, judge LLM, and inline `optimizations.training_datasets.lab22_qa_seed`. |
| `pyproject.toml` | dao-ai version pin (`>=0.1.90`). |

## Prerequisites

- Lab 21 completed (you already understand `agent.apredict` + `custom_outputs["trace_id"]`).
- Workspace access to:
  - MLflow 3 + Unity Catalog (any current FE workspace).
  - LLM endpoints `databricks-claude-sonnet-4-5` and `databricks-claude-haiku-4-5`
    (override via notebook widgets if you use different ones).
  - A UC catalog/schema where the lab can create the eval payload table and
    the external-dataset Delta table. Defaults to `main.dao_ai_workshop`.

## Run it

Open `notebook.py` in Databricks and Run All. The notebook handles per-student
naming via `WorkspaceClient.current_user`. Each scenario opens its own
`mlflow.start_run(...)` so the runs are easy to compare in the MLflow UI.

## Next

`lab-23-production-monitoring` takes the same agent and the same
`Guidelines`-style judges and runs them **continuously** against live traffic
via `dao_ai.evaluation.register_monitoring_scorers`.
