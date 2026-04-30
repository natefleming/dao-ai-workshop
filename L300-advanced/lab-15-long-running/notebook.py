# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 15 -- Long-Running / Background Agents
# MAGIC
# MAGIC **Level:** L300 (advanced)
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Configure `app.long_running:` so dao-ai wraps the agent with `LongRunningResponsesAgent`, persisting kickoff state in Lakebase.
# MAGIC - Sanity-check the agent with a synchronous in-notebook call (no `background`) to confirm the wrapper passes through normal requests unchanged.
# MAGIC - Deploy to Databricks Apps and exercise the **Responses-API contract end-to-end via HTTP** -- the way a real client process would. Three operations: **kickoff** (`background: true`), **retrieve** (`GET /v1/responses/{id}`), **cancel**.
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
print(f"Derived username: {username}")

dbutils.widgets.text("lakebase_project", "retail-consumer-goods", "Lakebase project")
dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-4-5", "LLM endpoint")
dbutils.widgets.text("max_duration_seconds", "1800", "Max background duration (s)")
dbutils.widgets.text("poll_interval_seconds", "1.0", "Internal poll cadence (s)")

params: dict[str, str] = {
    "username": username,
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
# MAGIC ## Step 5 -- Compile + sanity-check passthrough (no background)
# MAGIC
# MAGIC `mlflow.langchain.autolog()` registers tracers so we can see what the wrapped agent does. A synchronous call without `background: true` flows straight through the long-running wrapper's passthrough branch -- proves the agent is wired correctly before we deploy.

# COMMAND ----------

import mlflow

mlflow.langchain.autolog()

agent_lr = config.as_responses_agent()
print(f"Compiled app name: {config.app.name}")
print(f"Wrapped class:     {type(agent_lr).__name__}")

# COMMAND ----------

# Quick passthrough sanity check using the underlying graph (the
# long-running wrapper's kickoff/retrieve/cancel contract is best
# exercised against the deployed app — we do that in Steps 7-10 below).
from langgraph.graph.state import CompiledStateGraph

agent: CompiledStateGraph = config.as_graph()
sanity = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "In one sentence, what's the value of organizing inventory analysis as background work?"}]},
)
print(sanity["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 -- Deploy as a Databricks App

# COMMAND ----------

from dao_ai.config import DeploymentTarget

config.deploy_agent(target=DeploymentTarget.APPS)
print(f"Deployed app: {config.app.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 -- Wait for the deployed app to be ready
# MAGIC
# MAGIC The deploy returns once the bundle is uploaded; the app's Python process may still be starting. Poll until `compute_status.state == "ACTIVE"` and `app_status.state == "RUNNING"` before exercising the deployed surface.

# COMMAND ----------

info: dict[str, Any] = {}
for i in range(40):  # up to ~10 min
    info = w.api_client.do("GET", f"/api/2.0/apps/{config.app.name}")
    cs = (info.get("compute_status") or {}).get("state")
    aps = (info.get("app_status") or {}).get("state")
    print(f"  attempt {i+1:>2d}  compute={cs}  app={aps}")
    if cs == "ACTIVE" and aps == "RUNNING":
        break
    time.sleep(15)

app_url: str = info["url"]
print(f"\napp_url: {app_url}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 8 -- Kickoff: `POST /invocations` with `"background": true`
# MAGIC
# MAGIC Authenticates with `WorkspaceClient`'s bearer token and POSTs to `/invocations`. With `"background": true` the response returns immediately with a `resp_*` id and `status: in_progress`.

# COMMAND ----------

bearer: str = w.config.authenticate()["Authorization"].removeprefix("Bearer ")
hdr: dict[str, str] = {"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"}

t0 = time.time()
r = requests.post(
    f"{app_url}/invocations",
    headers=hdr,
    timeout=30,
    json={
        "input": [{"role": "user", "content": "Deep-research the Power Tools category for Q2 2026 and produce a thorough analyst report."}],
        "background": True,
        "custom_inputs": {"configurable": {"thread_id": f"lab15-{username}-deployed"}},
    },
)
r.raise_for_status()
kickoff: dict[str, Any] = r.json()
deployed_resp_id: str = kickoff["id"]
print(f"resp_id:  {deployed_resp_id}")
print(f"status:   {kickoff.get('status')}")
print(f"returned to client in {int((time.time()-t0)*1000)} ms (the agent is still working)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 9 -- Retrieve: poll `GET /v1/responses/{id}` until completed
# MAGIC
# MAGIC The deployed app exposes the OpenAI-Responses-style alias `/v1/responses/{id}` -- a strict GET that returns the latest state of the response (status + accumulated events + final output once the agent finishes). The actual analyst work takes ~30-90 seconds depending on FMAPI load.

# COMMAND ----------

t_start = time.time()
final_payload: dict[str, Any] = {}
for i in range(36):  # 36 * 5s = ~3 min cap
    r = requests.get(f"{app_url}/v1/responses/{deployed_resp_id}", headers=hdr, timeout=30)
    r.raise_for_status()
    final_payload = r.json()
    status = final_payload.get("status")
    print(f"  poll #{i+1:>2d} ({int(time.time()-t_start)}s)  status={status}")
    if status in ("completed", "failed", "cancelled"):
        break
    time.sleep(5)

print(f"\nfinal status: {final_payload.get('status')}")
if final_payload.get("status") == "completed":
    output = final_payload.get("output", [])
    if output:
        last = output[-1]
        content = last.get("content", [])
        if content:
            text = content[0].get("text", "")
            print(f"\n--- analyst report (first 800 chars) ---\n{text[:800]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 10 -- Cancel: kick off another task and cancel before it finishes
# MAGIC
# MAGIC Kicking off a second long task and immediately cancelling via `POST /invocations` with `operation: cancel`. The status flips to `cancelled` and the daemon thread tears down the underlying task best-effort.

# COMMAND ----------

# 10a -- kickoff
r = requests.post(
    f"{app_url}/invocations",
    headers=hdr,
    timeout=30,
    json={
        "input": [{"role": "user", "content": "Deep-research every category in our catalog and produce a 5000-word strategic review."}],
        "background": True,
        "custom_inputs": {"configurable": {"thread_id": f"lab15-{username}-cancel"}},
    },
)
r.raise_for_status()
cancel_kickoff = r.json()
cancel_resp_id: str = cancel_kickoff["id"]
print(f"resp_id:  {cancel_resp_id}")
print(f"status:   {cancel_kickoff.get('status')}  (cancelling immediately...)")

time.sleep(2)

# 10b -- cancel via /invocations + custom_inputs.operation
r = requests.post(
    f"{app_url}/invocations",
    headers=hdr,
    timeout=30,
    json={
        "input": [],
        "custom_inputs": {"operation": "cancel", "response_id": cancel_resp_id},
    },
)
r.raise_for_status()
cancelled = r.json()
print(f"cancelled.status: {cancelled.get('status')}")

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
