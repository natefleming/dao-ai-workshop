# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 15 -- Long-Running / Background Agents
# MAGIC
# MAGIC **Level:** L300 (advanced)
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Configure `app.long_running:` so dao-ai wraps the agent with `LongRunningResponsesAgent`, persisting kickoff state in Lakebase.
# MAGIC - Deploy to **both** targets (Apps for the chat-app slot, Model Serving for in-notebook SDK invocation) and exercise the **Responses-API contract end-to-end**. Three operations: **kickoff** (`background: true`), **retrieve** (`operation: retrieve`), **cancel** (`operation: cancel`).
# MAGIC - Show two SDK-clean invocation patterns from a notebook: `WorkspaceClient.serving_endpoints.http_request(...)` and `databricks_langchain.ChatDatabricks(..., responses_api=True)`.
# MAGIC - Understand why long-running agents need a checkpointer (state has to survive the kickoff / poll / cancel turns) and where dao-ai persists kickoff state.
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC A `hardware-store-<your-username>` agent that, when called with `background: true`, returns a `resp_*` ID immediately and produces a multi-paragraph inventory analysis ~30-90 seconds later -- retrievable by ID via the OpenAI-style `/v1/responses/{id}` route on the deployed app.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC **Use case:** `hardware_store++` -- inventory analyst agent that produces deep-research style reports.
# MAGIC
# MAGIC **DAO-AI concept:** `app.long_running:` block + `LongRunningResponsesAgent` wrapper + Lakebase-backed responses store + Responses-API HTTP surface (`/invocations` with `background: true`, `/v1/responses/{id}` for retrieve / cancel).
# MAGIC
# MAGIC ## Pre-reqs
# MAGIC
# MAGIC Same Lakebase / SP setup Lab 7 needs:
# MAGIC - `setup/create_service_principal.py` (creates the `dao-ai-workshop-sp` SP and the `dao_ai_workshop` secret scope).
# MAGIC - `setup/grant_lakebase_superuser.py` (grants the SP `DATABRICKS_SUPERUSER` on the Lakebase project).
# MAGIC - The `retail-consumer-goods` Lakebase autoscaling project must exist in the workspace.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 -- Install dependencies

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.66" "databricks-langchain>=0.7"
# MAGIC %restart_python

# COMMAND ----------

from importlib.metadata import version

print(f"dao-ai={version('dao-ai')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 -- Configure parameters

# COMMAND ----------

import re
import time
from typing import Any

from databricks.sdk import WorkspaceClient

w: WorkspaceClient = WorkspaceClient()
short_name: str = w.current_user.me().user_name.split("@")[0].lower()
username: str = re.sub(r"[^a-z0-9]+", "-", short_name).strip("-")[:13]
# SQL-safe variant for table names (hyphens aren't valid postgres identifiers).
username_sql: str = username.replace("-", "_")
print(f"Derived username: {username}  (sql-safe: {username_sql})")

dbutils.widgets.text("catalog", "workshop_nate_fleming", "Unity Catalog")
dbutils.widgets.text("schema", "dao_ai_workshop_test", "UC schema")
dbutils.widgets.text("lakebase_project", "retail-consumer-goods", "Lakebase project")
dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-4-5", "LLM endpoint")
dbutils.widgets.text("max_duration_seconds", "1800", "Max background duration (s)")
dbutils.widgets.text("poll_interval_seconds", "1.0", "Internal poll cadence (s)")

params: dict[str, str] = {
    "username": username,
    "username_sql": username_sql,
    "catalog": dbutils.widgets.get("catalog").strip(),
    "schema": dbutils.widgets.get("schema").strip(),
    "lakebase_project": dbutils.widgets.get("lakebase_project").strip(),
    "llm_endpoint": dbutils.widgets.get("llm_endpoint").strip(),
    "max_duration_seconds": dbutils.widgets.get("max_duration_seconds").strip(),
    "poll_interval_seconds": dbutils.widgets.get("poll_interval_seconds").strip(),
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 -- Provision the Lakebase postgres role for the SP
# MAGIC
# MAGIC `database.create()` creates a postgres role on the project's branch bound to the configured `client_id`, with `DATABRICKS_SUPERUSER` membership (same step as Lab 7). That gives the deployed app's SP schema-level CREATE on `public` so the long-running wrapper can run its table migrations on first request.

# COMMAND ----------

from dao_ai.config import AppConfig

config: AppConfig = AppConfig.from_file("background_advisor.yaml", params=params)

for s_key, schema in config.schemas.items():
    schema.create()
    print(f"UC schema ready: {s_key} -> {schema.full_name}")

for db_key, database in config.resources.databases.items():
    database.create()
    print(f"Lakebase role ready: {db_key} -> project={database.project}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- The `app.long_running:` block
# MAGIC
# MAGIC ```yaml
# MAGIC app:
# MAGIC   long_running:
# MAGIC     database: *workshop_db                       # same Lakebase the checkpointer uses
# MAGIC     default_background: false                    # caller opts in per-call
# MAGIC     max_duration_seconds: ${var.max_duration_seconds}
# MAGIC     poll_interval_seconds: ${var.poll_interval_seconds}
# MAGIC ```
# MAGIC
# MAGIC With this block present, dao-ai wraps the responses agent with `LongRunningResponsesAgent`. Two things happen on first request:
# MAGIC
# MAGIC 1. The wrapper auto-creates `dao_ai_responses` and `dao_ai_response_messages` tables in the Lakebase project (idempotent).
# MAGIC 2. Background runs go to a process-singleton daemon thread so they survive Model Serving's per-request `asyncio.run()` teardown.
# MAGIC
# MAGIC Three runtime operations are exposed (we exercise each below against the **deployed** endpoint -- the long-running pattern is a deployed-endpoint contract, not an in-notebook one):
# MAGIC
# MAGIC | client sends                                                                | server returns                                |
# MAGIC |---|---|
# MAGIC | `POST /invocations` with `"background": true`                              | immediate `resp_*` id, `status: in_progress`  |
# MAGIC | `GET /v1/responses/{id}` (or `POST /invocations` `operation: "retrieve"`)  | latest events / final output once `completed` |
# MAGIC | `POST /v1/responses/{id}/cancel` (or `operation: "cancel"`)                | best-effort cancel, `status: cancelled`       |

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 -- Compile + enable MLflow autolog
# MAGIC
# MAGIC `mlflow.langchain.autolog()` registers tracers so we can see what the wrapped agent does. `config.as_responses_agent()` returns a `LongRunningResponsesAgent` because the YAML has the `app.long_running:` block.
# MAGIC
# MAGIC We compile the agent here (and confirm the wrapped class) but **do not exercise the long-running contract in-process** -- that contract is a deployed-endpoint contract. The Lakebase responses tables are created and owned by the deployed app's service principal; an in-notebook call would connect with the user's PAT and hit `InsufficientPrivilege` on those tables. We exercise kickoff / retrieve / cancel against the deployed app in Step 7.

# COMMAND ----------

import mlflow

mlflow.langchain.autolog()

agent_lr = config.as_responses_agent()
print(f"Compiled app name: {config.app.name}")
print(f"Wrapped class:     {type(agent_lr).__name__}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 -- Deploy to BOTH (Apps + Model Serving)
# MAGIC
# MAGIC `create_agent()` logs a new MLflow model version; `deploy_agent(BOTH)` wires that version into both a Databricks App slot **and** a Model Serving endpoint named `endpoint_name`. The Apps URL is the workshop-standard chat-app slot; the MS endpoint is what we use below for SDK-clean in-notebook invocation.

# COMMAND ----------

from dao_ai.config import DeploymentTarget

config.create_agent()
config.deploy_agent(target=DeploymentTarget.BOTH)
print(f"Deployed: app slot=hardware-store-{username}, MS endpoint={config.app.endpoint_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 -- Invoke the deployed agent via the SDK (Model Serving endpoint)
# MAGIC
# MAGIC We invoke through the **Model Serving** endpoint because:
# MAGIC
# MAGIC - The SDK's `WorkspaceClient` already has workspace-scoped credentials. `/serving-endpoints/<name>/invocations` accepts those credentials directly -- no extra plumbing.
# MAGIC - The Apps URL (`*.databricksapps.com`) is fronted by gap-auth which expects an OAuth U2M session token, not a workspace-runtime token, so calling it from a notebook would 302 to OIDC authorize.
# MAGIC
# MAGIC Two equivalent SDK-clean clients are shown:
# MAGIC
# MAGIC | client                                                                           | what it gives you                                |
# MAGIC |---|---|
# MAGIC | `WorkspaceClient.api_client.do("POST", "/serving-endpoints/<name>/invocations", body=...)` | SDK-managed HTTP + auth, returns the parsed JSON envelope -- direct access to `id`, `status`, `output`, etc. |
# MAGIC | `databricks_langchain.ChatDatabricks(..., responses_api=True)`                   | LangChain `ChatModel` interface -- familiar `.invoke(messages, **kwargs)` shape |
# MAGIC
# MAGIC Either works for kickoff / retrieve / cancel by setting the right body fields (`background`, `custom_inputs.operation`, `response_id`).

# COMMAND ----------

# Wait for the MS endpoint to become READY.
# Right after deploy_agent(BOTH) the endpoint may take a moment to
# show up in the listing -- tolerate ResourceDoesNotExist for the
# first few polls.
from databricks.sdk.errors import ResourceDoesNotExist

endpoint_name: str = config.app.endpoint_name
for i in range(40):  # up to ~10 min
    try:
        ep = w.serving_endpoints.get(endpoint_name)
    except ResourceDoesNotExist:
        print(f"  attempt {i+1:>2d}  endpoint not yet visible, retrying...")
        time.sleep(15)
        continue
    ready = ep.state.ready if ep.state else None
    cfg_state = ep.state.config_update if ep.state else None
    print(f"  attempt {i+1:>2d}  ready={ready}  config={cfg_state}")
    if ready and str(ready).endswith("READY") and (cfg_state is None or str(cfg_state).endswith("NOT_UPDATING")):
        break
    time.sleep(15)

print(f"\nendpoint_name: {endpoint_name}")

# COMMAND ----------

# 7a -- kickoff via WorkspaceClient.api_client.do
ms_path: str = f"/serving-endpoints/{endpoint_name}/invocations"

t0 = time.time()
kickoff: dict[str, Any] = w.api_client.do(
    method="POST",
    path=ms_path,
    body={
        "input": [{"role": "user", "content": "Deep-research the Power Tools category for Q2 2026 and produce a thorough analyst report."}],
        "background": True,
        "custom_inputs": {"configurable": {"thread_id": f"lab15-{username}-deployed"}},
    },
)
deployed_resp_id: str = kickoff["id"]
print(f"[7a] kickoff ok: resp_id={deployed_resp_id}  status={kickoff.get('status')}  "
      f"({int((time.time()-t0)*1000)}ms)")

# COMMAND ----------

# 7b -- retrieve: poll with custom_inputs.operation = "retrieve"
t_start = time.time()
final_payload: dict[str, Any] = {}
for i in range(36):  # 36 * 5s = ~3 min cap
    final_payload = w.api_client.do(
        method="POST",
        path=ms_path,
        body={"input": [], "custom_inputs": {"operation": "retrieve", "response_id": deployed_resp_id}},
    )
    status = final_payload.get("status")
    print(f"  [7b] poll #{i+1:>2d} ({int(time.time()-t_start)}s)  status={status}")
    if status in ("completed", "failed", "cancelled"):
        break
    time.sleep(5)

if final_payload.get("status") == "completed":
    output = final_payload.get("output", [])
    if output and output[-1].get("content"):
        text = output[-1]["content"][0].get("text", "")
        print(f"\n--- deployed analyst report (first 800 chars) ---\n{text[:800]}")

# COMMAND ----------

# 7c -- cancel: kickoff again via ChatDatabricks (LangChain client), then cancel.
# Demonstrates the same MS endpoint reachable via databricks_langchain.
from databricks_langchain import ChatDatabricks

chat = ChatDatabricks(endpoint=endpoint_name, responses_api=True, max_tokens=2048)

cancel_kickoff = chat.invoke(
    [{"role": "user", "content": "Deep-research every category and produce a 5000-word strategic review."}],
    background=True,
    custom_inputs={"configurable": {"thread_id": f"lab15-{username}-deployed-cancel"}},
)
# ChatDatabricks returns an AIMessage with the kickoff envelope under
# `additional_kwargs` / `response_metadata` depending on version. Pull the id robustly.
cancel_id: str = (
    getattr(cancel_kickoff, "id", None)
    or cancel_kickoff.additional_kwargs.get("id")
    or cancel_kickoff.response_metadata.get("id")
)
print(f"[7c] kickoff (via ChatDatabricks): {cancel_id}  -- cancelling in 2s...")
time.sleep(2)

cancelled: dict[str, Any] = w.api_client.do(
    method="POST",
    path=ms_path,
    body={"input": [], "custom_inputs": {"operation": "cancel", "response_id": cancel_id}},
)
print(f"[7c] cancelled.status: {cancelled.get('status')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Streaming variant (no code, FYI)
# MAGIC
# MAGIC The deployed app also supports streaming both for synchronous calls and for retrieve. Add `"stream": true` to the `/invocations` body to get Server-Sent Events instead of a JSON envelope. We don't exercise streaming in this lab to keep the cell budget reasonable -- see `dao-ai/notebooks/14_long_running_agents_demo.py` for the full streaming demo.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next
# MAGIC
# MAGIC You've now seen every L300 pattern: instructed retrieval (Lab 11), Genie caching (Lab 12), programmatic construction (Lab 13), custom-input validation (Lab 14), and long-running agents (Lab 15). Re-read the L300 README's "what's next" section for production-deployment guidance.
