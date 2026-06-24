# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 22 -- Offline Evaluation with Judges and Datasets
# MAGIC
# MAGIC **Level:** L300
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Run `mlflow.genai.evaluate()` against the Lab 21 supervisor.
# MAGIC - Use a dao-ai config-defined inline dataset (Scenario A).
# MAGIC - Provision a UC Delta table and wrap it as a managed MLflow eval dataset (Scenario B).
# MAGIC - Author a custom `@scorer` (Scenario C).
# MAGIC - Apply per-row guidelines via `ExpectationsGuidelines` (Scenario D).
# MAGIC
# MAGIC ## Why this matters
# MAGIC
# MAGIC dao-ai ships first-class config for evaluation -- the `evaluation:` block
# MAGIC declares the judge LLM, guideline scorers, and the payload table, and
# MAGIC `optimizations.training_datasets` is dao-ai's validated registry for
# MAGIC inline `EvaluationDatasetModel` instances. Anything beyond that
# MAGIC (managed datasets from UC tables, custom `@scorer`s, per-row guidelines)
# MAGIC lives in MLflow's `mlflow.genai.*` namespace, and this lab shows how the
# MAGIC two surfaces compose.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 -- Install dependencies

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.98"
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

# Force synchronous trace export so the demo's tight loop is deterministic.
# Must be set BEFORE importing mlflow.
os.environ["MLFLOW_ENABLE_ASYNC_TRACE_LOGGING"] = "false"

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w: WorkspaceClient = WorkspaceClient()
short_name: str = w.current_user.me().user_name.split("@")[0].lower()
username: str = re.sub(r"[^a-z0-9]+", "-", short_name).strip("-")[:13]
USER: str = w.current_user.me().user_name
print(f"username: {username}")
print(f"user_id:  {USER}")

dbutils.widgets.text("catalog", "main", "UC catalog")
dbutils.widgets.text("schema", "dao_ai_workshop", "UC schema")
dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-4-5", "Default LLM")
dbutils.widgets.text("fast_llm_endpoint", "databricks-claude-haiku-4-5", "Fast LLM (tier-1)")
dbutils.widgets.text(
    "judge_llm_endpoint", "databricks-claude-sonnet-4-5", "Judge LLM"
)

params: dict[str, str] = {
    "username": username,
    "catalog": dbutils.widgets.get("catalog").strip(),
    "schema": dbutils.widgets.get("schema").strip(),
    "llm_endpoint": dbutils.widgets.get("llm_endpoint").strip(),
    "fast_llm_endpoint": dbutils.widgets.get("fast_llm_endpoint").strip(),
    "judge_llm_endpoint": dbutils.widgets.get("judge_llm_endpoint").strip(),
}
print(params)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 -- Build the agent

# COMMAND ----------

import mlflow

from dao_ai.config import AppConfig

# Autolog opens the langchain root trace. ``run_tracer_inline=True`` makes
# the autologged trace synchronous with ``mlflow.genai.evaluate``'s harness
# so the harness reuses the autologged trace instead of creating a 0s
# placeholder trace alongside it (dao-ai's notebooks/08_run_evaluation.py
# uses the same pattern). The disable-then-re-enable clears any workspace
# global autolog that might otherwise stack on top.
mlflow.autolog(disable=True)
mlflow.langchain.autolog(run_tracer_inline=True)

# Use a named workspace experiment so every scenario's runs land in a
# stable, discoverable location. mlflow.set_experiment creates the
# experiment on first call and returns it on every subsequent one.
experiment = mlflow.set_experiment(f"/Users/{USER}/Lab22-evaluation")
experiment_id: str = experiment.experiment_id
print(f"experiment: {experiment.name} ({experiment_id})")

config: AppConfig = AppConfig.from_file("evaluation_agent.yaml", params=params)

# Provision the UC schema for the evaluation payload table and the
# external-dataset Delta table later in this notebook.
for schema in config.schemas.values():
    schema.create()

agent = config.as_responses_agent()
print(f"App: {config.app.name}")
print(f"Agents: {[a.name for a in config.app.agents]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- Define `predict_fn` for `mlflow.genai.evaluate`
# MAGIC
# MAGIC Passing `predict_fn=` to `mlflow.genai.evaluate` makes the harness run
# MAGIC the agent itself, producing exactly **one trace per evaluation row**
# MAGIC with the assessment values attached. The signature has to accept
# MAGIC every key that the dataset's `inputs` dict carries -- dao-ai's
# MAGIC `ChatPayload` dumps three keys (`input`, `messages`, `custom_inputs`),
# MAGIC so the function declares all three even though only `messages` is
# MAGIC used.
# MAGIC
# MAGIC A `threading.Lock` serialises the agent call since the harness
# MAGIC parallelises rows across worker threads.
# MAGIC
# MAGIC > Heads-up on runtime quirks: in the Step 3 cell we call
# MAGIC > `mlflow.langchain.autolog(run_tracer_inline=True)`. That mode makes
# MAGIC > the autologged trace synchronous with the harness's row execution
# MAGIC > so each row gets exactly one trace -- without it the harness can
# MAGIC > race the trace exporter and emit duplicate (or null-assessment)
# MAGIC > traces. dao-ai's own `notebooks/08_run_evaluation.py` uses the
# MAGIC > same pattern.

# COMMAND ----------

import threading
from typing import Any

from mlflow.types.responses import ResponsesAgentRequest, ResponsesAgentResponse

_predict_lock = threading.Lock()


def _extract_output_text(response: ResponsesAgentResponse) -> str:
    texts: list[str] = []
    for output in response.output:
        if isinstance(output, dict):
            if output.get("type") == "message":
                for content in output.get("content", []):
                    if isinstance(content, dict) and "text" in content:
                        texts.append(content.get("text", ""))
        elif getattr(output, "type", None) == "message":
            for content in output.content:
                if isinstance(content, dict) and "text" in content:
                    texts.append(content.get("text", ""))
                elif getattr(content, "type", None) == "output_text":
                    texts.append(content.text)
    return "".join(texts) if texts else str(response.output)


def predict_fn(
    messages: list[dict[str, Any]] | None = None,
    input: list[dict[str, Any]] | None = None,
    custom_inputs: dict[str, Any] | None = None,
) -> str:
    """Run one agent turn for an evaluation row.

    Accepts all three keys ChatPayload.model_dump emits so MLflow's
    signature validator doesn't reject the call.
    """
    msgs = messages or input or []
    with _predict_lock:
        request = ResponsesAgentRequest(
            input=[{"role": m["role"], "content": m["content"]} for m in msgs],
            custom_inputs={
                "configurable": {"user_id": USER},
                "session": {},
            },
        )
        response: ResponsesAgentResponse = asyncio.run(agent.apredict(request))
        return _extract_output_text(response)


# Smoke-test predict_fn end-to-end before evaluation runs.
sample_out: str = predict_fn(
    messages=[{"role": "user", "content": "How do I reset my password?"}]
)
print(f"sample response ({len(sample_out)} chars): {sample_out[:200]}...")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Scenario A -- Config-defined inline dataset + built-in scorers + Guidelines
# MAGIC
# MAGIC The YAML declared `optimizations.training_datasets.lab22_qa_seed` with
# MAGIC six entries (`inputs.messages` + `expectations.expected_facts`).
# MAGIC `EvaluationDatasetModel.as_dataset()` creates (or reuses) the managed
# MAGIC MLflow dataset and merges the inline entries.
# MAGIC
# MAGIC `dao_ai.evaluation.build_scorers(config.evaluation)` returns:
# MAGIC
# MAGIC | Scorer | Source |
# MAGIC |---|---|
# MAGIC | `Safety()` | built-in |
# MAGIC | `Completeness()` | built-in |
# MAGIC | `RelevanceToQuery()` | built-in |
# MAGIC | `ToolCallEfficiency()` | built-in |
# MAGIC | `Guidelines(name="routing_quality", ...)` | from YAML |
# MAGIC | `Guidelines(name="response_quality", ...)` | from YAML |
# MAGIC
# MAGIC We append `Correctness()` manually so the `expected_facts` in the
# MAGIC dataset get scored too.

# COMMAND ----------

from datetime import datetime

from mlflow.genai.scorers import Correctness
from mlflow.models.evaluation import EvaluationResult

from dao_ai.evaluation import build_scorers, prepare_eval_results_for_display

# (1) Register the inline dataset as a managed MLflow dataset in UC.
seed_ds = config.optimizations.training_datasets["lab22_qa_seed"].as_dataset()
print(f"Dataset name: {seed_ds.name}")
print(f"Dataset id:   {seed_ds.dataset_id}")
print(f"Record count: {len(seed_ds.to_df())}")

# (2) Materialise the inline entries from YAML into eval records. predict_fn
#     will be invoked by the harness for each row -- one trace per row, with
#     assessment values attached.
seed_records: list[dict[str, Any]] = []
for entry in config.optimizations.training_datasets["lab22_qa_seed"].data:
    seed_records.append({
        "inputs": {"messages": [m.model_dump() for m in entry.inputs.messages]},
        # Correctness reads expectations.expected_facts; nesting matters.
        "expectations": {"expected_facts": entry.expectations.expected_facts},
    })
print(f"\nPrepared {len(seed_records)} eval records for Scenario A")

# (3) Build the scorers. build_scorers() returns Safety + Completeness +
#     RelevanceToQuery + ToolCallEfficiency + the two Guidelines scorers
#     declared in config.evaluation.guidelines. We add Correctness so the
#     expected_facts get scored too.
base_scorers = build_scorers(config.evaluation)
scorers_a = [*base_scorers, Correctness()]
print(f"Scorers: {[getattr(s, 'name', type(s).__name__) for s in scorers_a]}")

run_name_a: str = f"lab22_scenario_a_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
with mlflow.start_run(run_name=run_name_a) as run_a:
    eval_results_a: EvaluationResult = mlflow.genai.evaluate(
        data=seed_records,
        predict_fn=predict_fn,
        scorers=scorers_a,
    )

print(f"\nRun id: {run_a.info.run_id}")
print("Metrics:")
for k, v in (eval_results_a.metrics or {}).items():
    print(f"  {k}: {v}")

display(prepare_eval_results_for_display(eval_results_a))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Scenario B -- UC Delta table -> managed MLflow dataset
# MAGIC
# MAGIC Any UC-resident table is one `merge_records` call away from being a
# MAGIC versioned MLflow dataset. The workflow:
# MAGIC
# MAGIC 1. Write rows to a UC Delta table (here: `${catalog}.${schema}.lab22_eval_external`).
# MAGIC 2. Create or fetch a managed MLflow dataset by name.
# MAGIC 3. Merge the table rows into the dataset.
# MAGIC 4. Pass the dataset directly to `mlflow.genai.evaluate(data=...)`.

# COMMAND ----------

import pandas as pd
from mlflow.genai.datasets import create_dataset, get_dataset

catalog: str = params["catalog"]
schema_name: str = params["schema"]
external_table: str = f"{catalog}.{schema_name}.lab22_eval_external"
external_ds_name: str = f"{catalog}.{schema_name}.lab22_eval_external_ds"

external_records: list[dict[str, Any]] = [
    {
        "inputs": {"messages": [{"role": "user", "content": "How do I rotate an API key?"}]},
        "expectations": {"expected_facts": [
            "Account or API settings section is referenced",
            "A concrete next action is provided to the user",
        ]},
    },
    {
        "inputs": {"messages": [{"role": "user", "content": "What is the timezone of the audit log timestamps?"}]},
        "expectations": {"expected_facts": [
            "UTC or ISO-8601 is mentioned",
            "The response stays on policy and does not invent a different timezone",
        ]},
    },
    {
        "inputs": {"messages": [{"role": "user", "content": "The webhook delivery dashboard shows status=pending for 10 minutes."}]},
        "expectations": {"expected_facts": [
            "Retry policy or backoff is referenced",
            "A concrete diagnostic step is recommended",
        ]},
    },
    {
        "inputs": {"messages": [{"role": "user", "content": "Our SSO group sync is missing three users that exist in our IdP."}]},
        "expectations": {"expected_facts": [
            "Group filter, SCIM, or attribute mapping is referenced",
            "A concrete diagnostic step is recommended",
        ]},
    },
    {
        "inputs": {"messages": [{"role": "user", "content": "The CLI hangs forever on `init` without writing any output."}]},
        "expectations": {"expected_facts": [
            "Verbose flag, logs, or network reachability is mentioned",
            "A concrete diagnostic step is recommended",
        ]},
    },
]

external_df: pd.DataFrame = pd.DataFrame(external_records)
(
    spark.createDataFrame(external_df)
    .write.mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(external_table)
)
print(f"Wrote {len(external_df)} rows to {external_table}")

# COMMAND ----------

try:
    external_ds = get_dataset(name=external_ds_name)
    print(f"Reusing external dataset {external_ds.name} ({external_ds.dataset_id})")
except Exception:
    external_ds = create_dataset(name=external_ds_name, experiment_id=experiment_id)
    print(f"Created external dataset {external_ds.name} ({external_ds.dataset_id})")

external_ds = external_ds.merge_records(external_df)
print(f"Records after merge: {len(external_ds.to_df())}")

# COMMAND ----------

run_name_b: str = f"lab22_scenario_b_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
with mlflow.start_run(run_name=run_name_b) as run_b:
    eval_results_b: EvaluationResult = mlflow.genai.evaluate(
        data=external_records,
        predict_fn=predict_fn,
        scorers=[*base_scorers, Correctness()],
    )

print("Metrics:")
for k, v in (eval_results_b.metrics or {}).items():
    print(f"  {k}: {v}")
display(prepare_eval_results_for_display(eval_results_b))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Scenario C -- Custom `@scorer`
# MAGIC
# MAGIC The built-in + Guidelines scorers cover most quality dimensions, but
# MAGIC sometimes the metric is mechanical (length, presence of a keyword,
# MAGIC structured-output validity). For those, a custom `@scorer` returning
# MAGIC a `Feedback` is one function call.

# COMMAND ----------

from mlflow.entities import Feedback
from mlflow.genai.scorers import scorer


@scorer
def includes_concrete_step(outputs: str) -> Feedback:
    """Pass if the response mentions a concrete user-facing action verb."""
    action_verbs: tuple[str, ...] = (
        "open ", "click ", "navigate", "run ", "set ", "check ",
        "verify", "review", "configure", "enable", "disable",
        "go to", "look at", "inspect", "send ",
    )
    response_lc: str = (outputs or "").lower()
    matched: list[str] = [v for v in action_verbs if v in response_lc]
    if matched:
        return Feedback(value=True, rationale=f"matched action verb(s): {matched[:3]}")
    return Feedback(value=False, rationale="no concrete action verb in the response")


# Reuses Scenario A's seed_records (same agent will run again per row).
run_name_c: str = f"lab22_scenario_c_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
with mlflow.start_run(run_name=run_name_c) as run_c:
    eval_results_c: EvaluationResult = mlflow.genai.evaluate(
        data=seed_records,
        predict_fn=predict_fn,
        scorers=[*base_scorers, Correctness(), includes_concrete_step],
    )

print("Metrics:")
for k, v in (eval_results_c.metrics or {}).items():
    print(f"  {k}: {v}")
display(prepare_eval_results_for_display(eval_results_c))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Scenario D -- Per-row guidelines via `ExpectationsGuidelines`
# MAGIC
# MAGIC When the guideline varies by row -- e.g. tier-2 answers must reference
# MAGIC logs but tier-1 answers don't -- per-row guidelines beat a single
# MAGIC global rule. Set `expectations.guidelines` on each row and add the
# MAGIC `ExpectationsGuidelines()` scorer; MLflow evaluates each row against
# MAGIC its own list.

# COMMAND ----------

from mlflow.genai.scorers import ExpectationsGuidelines

per_row: list[dict[str, Any]] = [
    {
        "inputs": {"messages": [{"role": "user", "content": "How do I change my account display name?"}]},
        "expectations": {
            "guidelines": [
                "The response is concise (under 5 sentences)",
                "The response references account or profile settings",
            ],
        },
    },
    {
        "inputs": {"messages": [{"role": "user", "content": "Production traffic is hitting HTTP 502 on /v1/sync every few minutes."}]},
        "expectations": {
            "guidelines": [
                "The response references logs OR error-correlation IDs",
                "The response recommends at least one specific diagnostic step",
            ],
        },
    },
    {
        "inputs": {"messages": [{"role": "user", "content": "Our cron job hits rate limits at 03:00 UTC every day."}]},
        "expectations": {
            "guidelines": [
                "The response references rate limit headers OR retry-after",
                "The response recommends at least one specific diagnostic step",
            ],
        },
    },
]

run_name_d: str = f"lab22_scenario_d_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
with mlflow.start_run(run_name=run_name_d) as run_d:
    eval_results_d: EvaluationResult = mlflow.genai.evaluate(
        data=per_row,
        predict_fn=predict_fn,
        scorers=[ExpectationsGuidelines(), *base_scorers],
    )

print("Metrics:")
for k, v in (eval_results_d.metrics or {}).items():
    print(f"  {k}: {v}")
display(prepare_eval_results_for_display(eval_results_d))

# COMMAND ----------

# MAGIC %md
# MAGIC ## What you just did
# MAGIC
# MAGIC | Scenario | Dataset source | Scorers |
# MAGIC |---|---|---|
# MAGIC | A | `optimizations.training_datasets` in YAML | `build_scorers(config.evaluation)` + `Correctness` |
# MAGIC | B | UC Delta table -> `mlflow.genai.datasets.create_dataset(...).merge_records(df)` | same as A |
# MAGIC | C | Same inline dataset as A | A's scorers + a custom `@scorer` returning `Feedback` |
# MAGIC | D | In-memory `list[dict]` with `expectations.guidelines` per row | `ExpectationsGuidelines` + built-in scorers |
# MAGIC
# MAGIC The next lab (`lab-23-production-monitoring`) takes the same agent and
# MAGIC the same `Guidelines`-style judges and runs them **continuously**
# MAGIC against live traffic via `dao_ai.evaluation.register_monitoring_scorers`.
