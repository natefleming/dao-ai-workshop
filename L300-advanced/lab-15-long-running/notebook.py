# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 15 -- Long-Running / Background Agents
# MAGIC
# MAGIC **Level:** L300 (advanced)
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Configure `app.long_running:` so dao-ai wraps the agent with `LongRunningResponsesAgent`, persisting kickoff state in Lakebase.
# MAGIC - Exercise the Responses-API contract end-to-end **inside the notebook**: kickoff (`background: true`), retrieve (`operation: "retrieve"`), cancel (`operation: "cancel"`).
# MAGIC - Hit the **same surface on the deployed Databricks App** (`/invocations` + `/v1/responses/{id}`) using `WorkspaceClient` to authenticate and `requests` to call out -- the way a real client process would.
# MAGIC - Understand why long-running agents need a checkpointer (state has to survive across kickoff/poll turns).
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC A `hardware-store-<your-username>` agent that, when called with `background: true`, returns a `resp_*` ID immediately and produces a multi-paragraph inventory analysis ~30-90 seconds later -- retrievable by ID either in-notebook (`predict({...operation: retrieve...})`) or against the deployed app (`GET /v1/responses/{id}`).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC **Use case:** `hardware_store++` -- inventory analyst agent that produces deep-research style reports.
# MAGIC
# MAGIC **DAO-AI concept:** `app.long_running:` block + `LongRunningResponsesAgent` wrapper + Lakebase-backed responses store.
# MAGIC
# MAGIC ## Pre-reqs
# MAGIC
# MAGIC Same Lakebase / SP setup Lab 7 needs:
# MAGIC - `setup/create_service_principal.sh` (creates the `dao-ai-workshop-sp` SP and the `dao_ai_workshop` secret scope).
# MAGIC - `setup/grant_lakebase_superuser.sh` (grants the SP `DATABRICKS_SUPERUSER` on the Lakebase project).
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

from databricks.sdk import WorkspaceClient
from langgraph.graph.state import CompiledStateGraph

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
# MAGIC With this block present, `config.as_responses_agent()` returns a `LongRunningResponsesAgent` instead of the plain `ResponsesAgent`. Two things happen on first request:
# MAGIC
# MAGIC 1. The wrapper auto-creates `dao_ai_responses` and `dao_ai_response_messages` tables in the Lakebase project (idempotent).
# MAGIC 2. Background runs go to a process-singleton daemon thread so they survive Model Serving's per-request `asyncio.run()` teardown.
# MAGIC
# MAGIC Three runtime operations are exposed:
# MAGIC
# MAGIC | client sends                                                                | server returns                              |
# MAGIC |---|---|
# MAGIC | `custom_inputs={"background": true}`                                        | immediate `resp_*` id, `status: in_progress` |
# MAGIC | `custom_inputs={"operation": "retrieve", "response_id": id}`                | latest events / final output once `completed` |
# MAGIC | `custom_inputs={"operation": "cancel",   "response_id": id}`                | best-effort cancel, `status: cancelled`      |

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 -- Compile the responses agent + enable MLflow autolog

# COMMAND ----------

import mlflow

mlflow.langchain.autolog()

agent_lr = config.as_responses_agent()

print(f"Compiled app name: {config.app.name}")
print(f"Wrapped class:     {type(agent_lr).__name__}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 -- Exercise kickoff / retrieve / cancel locally
# MAGIC
# MAGIC `dao_ai.models.process_messages(...)` accepts the responses-agent + a list of messages + `custom_inputs={...}` and returns the response object.

# COMMAND ----------

from dao_ai.models import process_messages

# COMMAND ----------

# MAGIC %md
# MAGIC ### 6a. Kickoff -- background: true returns a resp_* id immediately

# COMMAND ----------

t0 = time.time()
kickoff = process_messages(
    agent_lr,
    [{"role": "user", "content": "Deep-research the Power Tools category for Q2 2026 and produce a thorough analyst report."}],
    custom_inputs={
        "configurable": {"thread_id": f"lab15-{username}-A"},
        "background": True,
    },
)
elapsed_ms = int((time.time() - t0) * 1000)
resp_id_a: str = kickoff.id  # type: ignore[attr-defined]
print(f"resp_id:  {resp_id_a}")
print(f"status:   {kickoff.status}")
print(f"returned to client in {elapsed_ms} ms (the agent is still working)")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 6b. Retrieve -- poll until status: completed
# MAGIC
# MAGIC The actual analyst work (multi-paragraph report) takes ~30-90 seconds depending on FMAPI load. We poll every 5 seconds for up to ~3 minutes.

# COMMAND ----------

t_start = time.time()
final = None
for i in range(36):  # 36 * 5s = ~3 min cap
    final = process_messages(
        agent_lr,
        [],  # retrieve doesn't need new messages
        custom_inputs={"operation": "retrieve", "response_id": resp_id_a},
    )
    print(f"  poll #{i+1:>2d} ({int(time.time()-t_start)}s)  status={final.status}")
    if final.status in ("completed", "failed", "cancelled"):
        break
    time.sleep(5)

print(f"\nfinal status: {final.status}")
if final.status == "completed":
    # output[-1] is the final assistant message; .content[0].text is the body.
    block = final.output[-1].content[0]
    text = getattr(block, "text", None) or block["text"]
    print(f"\n--- analyst report (first 800 chars) ---\n{text[:800]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 6c. Cancel -- kick off a second task and cancel it before it finishes

# COMMAND ----------

cancel_kickoff = process_messages(
    agent_lr,
    [{"role": "user", "content": "Deep-research every category in our catalog and produce a 5000-word strategic review."}],
    custom_inputs={
        "configurable": {"thread_id": f"lab15-{username}-B"},
        "background": True,
    },
)
resp_id_b: str = cancel_kickoff.id  # type: ignore[attr-defined]
print(f"resp_id:  {resp_id_b}")
print(f"status:   {cancel_kickoff.status}  (cancelling immediately...)")

# Give the daemon thread a moment to start the work, then cancel.
time.sleep(2)

cancelled = process_messages(
    agent_lr,
    [],
    custom_inputs={"operation": "cancel", "response_id": resp_id_b},
)
print(f"cancelled.status: {cancelled.status}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Streaming variant (no code, FYI)
# MAGIC
# MAGIC `LongRunningResponsesAgent` also supports streaming retrieve via `agent_lr.predict_stream(...)` (or, on the deployed app, `POST /invocations` with `"stream": true`). The server emits Server-Sent Events as the agent generates each chunk. We don't exercise streaming in this lab to keep the cell budget reasonable -- see `dao-ai/notebooks/14_long_running_agents_demo.py` for the full streaming demo.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 -- Deploy as a Databricks App

# COMMAND ----------

from dao_ai.config import DeploymentTarget

config.deploy_agent(target=DeploymentTarget.APPS)
print(f"Deployed app: {config.app.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 8 -- Wait for the deployed app's compute to be ready
# MAGIC
# MAGIC The deploy returns once the bundle is uploaded; the App's Python process may still be starting. Poll until `compute_status.state == "ACTIVE"` and `app_status.state == "RUNNING"` before exercising the deployed surface.

# COMMAND ----------

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
# MAGIC ## Step 9 -- Invoke the deployed app from a client (WorkspaceClient + requests)
# MAGIC
# MAGIC This is what a real client process (a script, a backend, another notebook) would do: get the app URL via `WorkspaceClient`, mint a bearer token, POST to `/invocations` with `"background": true`, and poll the Responses-API alias `/v1/responses/{id}` until done.
# MAGIC
# MAGIC Compare to Step 6 (which talks to the in-process compiled graph) -- the surface is identical, the wire path is different. dao-ai mounts strict `/v1/responses*` routes on Databricks Apps so the deployed agent is a drop-in for any OpenAI-Responses-compatible client.

# COMMAND ----------

import requests

bearer: str = w.config.authenticate()["Authorization"].removeprefix("Bearer ")
hdr: dict[str, str] = {"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"}

# 9a -- kickoff via /invocations
t0 = time.time()
r = requests.post(
    f"{app_url}/invocations",
    headers=hdr,
    timeout=30,
    json={
        "input": [{"role": "user", "content": "Deep-research the Hand Tools category and produce a thorough analyst report."}],
        "custom_inputs": {
            "configurable": {"thread_id": f"lab15-{username}-deployed"},
            "background": True,
        },
    },
)
r.raise_for_status()
kickoff_payload: dict[str, Any] = r.json()
deployed_resp_id: str = kickoff_payload["id"]
print(f"deployed kickoff status: {kickoff_payload.get('status')}  (id={deployed_resp_id}, returned in {int((time.time()-t0)*1000)}ms)")

# COMMAND ----------

# 9b -- poll /v1/responses/{id}
t_start = time.time()
final_payload: dict[str, Any] = {}
for i in range(36):  # 36 * 5s = ~3 min
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
        # output[-1] is the assistant message; content[0].text is the body.
        content = last.get("content", [])
        if content:
            text = content[0].get("text", "")
            print(f"\n--- deployed analyst report (first 800 chars) ---\n{text[:800]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next
# MAGIC
# MAGIC You've now seen every L300 pattern: instructed retrieval (Lab 11), Genie caching (Lab 12), programmatic construction (Lab 13), custom-input validation (Lab 14), and long-running agents (Lab 15). Re-read the L300 README's "what's next" section for production-deployment guidance.
