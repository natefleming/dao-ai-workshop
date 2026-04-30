# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 15 -- Long-Running / Background Agents
# MAGIC
# MAGIC **Level:** L300 (advanced)
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Configure `app.long_running:` so dao-ai wraps the agent with `LongRunningResponsesAgent`, persisting kickoff state in Lakebase.
# MAGIC - Deploy to **Model Serving** (`deployment_target: model_serving`) and exercise the **Responses-API contract end-to-end via HTTP** -- the way a real client process would. Three operations: **kickoff** (`background: true`), **retrieve** (`operation: retrieve`), **cancel** (`operation: cancel`).
# MAGIC - Understand why long-running agents need a checkpointer (state has to survive the kickoff / poll / cancel turns) and why the contract is a deployed-endpoint contract -- the responses tables are owned by the deployed agent's service principal, so an in-notebook predict (under the user's PAT) would hit `InsufficientPrivilege`.
# MAGIC - Notice why this lab targets Model Serving instead of Apps: MS's `/serving-endpoints/<name>/invocations` accepts the notebook's SDK bearer; Apps live behind gap-auth and require a CLI-minted OAuth token.
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

# MAGIC %pip install "dao-ai>=0.1.66"
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

import requests
from databricks.sdk import WorkspaceClient

w: WorkspaceClient = WorkspaceClient()
short_name: str = w.current_user.me().user_name.split("@")[0].lower()
username: str = re.sub(r"[^a-z0-9]+", "-", short_name).strip("-")[:13]
# SQL-safe variant for table names (hyphens aren't valid postgres identifiers).
username_sql: str = username.replace("-", "_")
print(f"Derived username: {username}  (sql-safe: {username_sql})")

dbutils.widgets.text("lakebase_project", "retail-consumer-goods", "Lakebase project")
dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-4-5", "LLM endpoint")
dbutils.widgets.text("max_duration_seconds", "1800", "Max background duration (s)")
dbutils.widgets.text("poll_interval_seconds", "1.0", "Internal poll cadence (s)")

params: dict[str, str] = {
    "username": username,
    "username_sql": username_sql,
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
# MAGIC ## Step 6 -- Deploy to Model Serving
# MAGIC
# MAGIC `create_agent()` logs a new MLflow model version; `deploy_agent()` wires that version into a Model Serving endpoint named `config.app.name`. (`deploy_agent` alone errors when the endpoint already serves the latest version, hence the explicit `create_agent()` first.)

# COMMAND ----------

from dao_ai.config import DeploymentTarget

config.create_agent()
config.deploy_agent(target=DeploymentTarget.MODEL_SERVING)
print(f"Deployed serving endpoint: {config.app.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 -- Invoke the deployed Model Serving endpoint
# MAGIC
# MAGIC Real client processes (a backend service, a script, another notebook) call the endpoint over HTTP. Pattern:
# MAGIC
# MAGIC 1. Resolve the workspace host from `WorkspaceClient.config`.
# MAGIC 2. Mint a bearer token from the same client (`w.config.authenticate()`).
# MAGIC 3. **Kickoff:** `POST <host>/serving-endpoints/<name>/invocations` with `"background": true` -- returns a `resp_*` id and `status: in_progress` within ~1s.
# MAGIC 4. **Retrieve:** repeat `POST` with `custom_inputs.operation: "retrieve"` until `status: completed`. (Apps also expose `GET /v1/responses/{id}` -- Model Serving does not, so we use the `operation: retrieve` form.)
# MAGIC 5. **Cancel:** `POST` with `custom_inputs.operation: "cancel"` flips the status to `cancelled`.
# MAGIC
# MAGIC We deploy to Model Serving (not Databricks Apps) because the long-running pattern is a headless API contract: MS accepts the notebook's SDK bearer for `/serving-endpoints/<name>/invocations`. Apps live behind gap-auth, which rejects in-notebook tokens with a 302 to OIDC -- usable only from a CLI-minted OAuth client.

# COMMAND ----------

# Wait for the endpoint to become READY.
endpoint_name: str = config.app.name
for i in range(40):  # up to ~10 min
    ep = w.serving_endpoints.get(endpoint_name)
    state = ep.state.ready if ep.state else None
    cfg_state = ep.state.config_update if ep.state else None
    print(f"  attempt {i+1:>2d}  ready={state}  config={cfg_state}")
    if state and str(state).endswith("READY"):
        break
    time.sleep(15)

ms_url: str = f"{w.config.host.rstrip('/')}/serving-endpoints/{endpoint_name}/invocations"
print(f"\nms_url: {ms_url}")

# COMMAND ----------

bearer: str = w.config.authenticate()["Authorization"].removeprefix("Bearer ")
hdr: dict[str, str] = {"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"}

# 7a -- kickoff via POST /serving-endpoints/<name>/invocations
t0 = time.time()
r = requests.post(
    ms_url,
    headers=hdr,
    timeout=60,
    json={
        "input": [{"role": "user", "content": "Deep-research the Power Tools category for Q2 2026 and produce a thorough analyst report."}],
        "background": True,
        "custom_inputs": {"configurable": {"thread_id": f"lab15-{username}-deployed"}},
    },
)
r.raise_for_status()
kickoff: dict[str, Any] = r.json()
deployed_resp_id: str = kickoff["id"]
print(f"[7a] kickoff ok: resp_id={deployed_resp_id}  status={kickoff.get('status')}  "
      f"({int((time.time()-t0)*1000)}ms)")

# COMMAND ----------

# 7b -- retrieve via POST with operation=retrieve
t_start = time.time()
final_payload: dict[str, Any] = {}
for i in range(36):  # 36 * 5s = ~3 min cap
    r = requests.post(
        ms_url,
        headers=hdr,
        timeout=30,
        json={"input": [], "custom_inputs": {"operation": "retrieve", "response_id": deployed_resp_id}},
    )
    r.raise_for_status()
    final_payload = r.json()
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

# 7c -- cancel: kickoff again, immediately cancel
r = requests.post(
    ms_url,
    headers=hdr,
    timeout=60,
    json={
        "input": [{"role": "user", "content": "Deep-research every category and produce a 5000-word strategic review."}],
        "background": True,
        "custom_inputs": {"configurable": {"thread_id": f"lab15-{username}-deployed-cancel"}},
    },
)
r.raise_for_status()
cancel_id: str = r.json()["id"]
print(f"[7c] kickoff: {cancel_id}  -- cancelling in 2s...")
time.sleep(2)
r = requests.post(
    ms_url,
    headers=hdr,
    timeout=30,
    json={"input": [], "custom_inputs": {"operation": "cancel", "response_id": cancel_id}},
)
r.raise_for_status()
print(f"[7c] cancelled.status: {r.json().get('status')}")

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
