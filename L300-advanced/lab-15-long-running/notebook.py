# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 15 -- Long-Running / Background Agents
# MAGIC
# MAGIC **Level:** L300 (advanced)
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Configure `app.long_running:` so dao-ai wraps the agent with `LongRunningResponsesAgent`, persisting kickoff state in Lakebase.
# MAGIC - Deploy as a Databricks App and exercise the **Responses-API contract end-to-end**: kickoff (`background=True`), retrieve, cancel.
# MAGIC - Show the canonical pattern for invoking an Apps-deployed agent from a notebook: OIDC token-exchange to mint an app-scoped OAuth bearer, then the OpenAI Python SDK against the App URL.
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

# MAGIC %pip install "dao-ai>=0.1.66" "openai>=1.40"
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
# MAGIC ## Step 6 -- Deploy as a Databricks App

# COMMAND ----------

from dao_ai.config import DeploymentTarget

config.deploy_agent(target=DeploymentTarget.APPS)
print(f"Deployed app: {config.app.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 -- Invoke the deployed App from a notebook
# MAGIC
# MAGIC The Apps URL (`*.databricksapps.com`) is fronted by **gap-auth**, an OAuth proxy that requires an audience-scoped OAuth U2M token (NOT a workspace-runtime token). A notebook's default `WorkspaceClient` has a runtime PAT, so calling `/invocations` directly with `w.config.authenticate()` returns `HTTP 302` to `/oidc/oauth2/v2.0/authorize`.
# MAGIC
# MAGIC The canonical fix is the **Databricks token-exchange endpoint** (`POST /oidc/v1/token`): exchange the notebook's PAT for an OAuth access token whose `audience` is the App's OAuth client ID. Pure Python, no CLI, no shell:
# MAGIC
# MAGIC ```text
# MAGIC notebook PAT  --[POST /oidc/v1/token, audience=<app_client_id>]-->  app-scoped OAuth bearer  -->  POST /invocations
# MAGIC ```
# MAGIC
# MAGIC Once we have the bearer, we use Databricks' canonical client for Apps inference: **`databricks_openai.DatabricksOpenAI`** with `model="apps/<app-name>"`. It auto-resolves the App URL, manages the HTTP client, and exposes the OpenAI Responses API surface (`responses.create`, `responses.retrieve`, `responses.cancel`).
# MAGIC
# MAGIC Refs (canonical Databricks docs):
# MAGIC - [Query an agent deployed on Databricks](https://docs.databricks.com/aws/en/generative-ai/agent-framework/query-agent) -- the `DatabricksOpenAI` + `apps/<name>` pattern.
# MAGIC - [Connect to a Databricks App with token authentication](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/connect-local) -- the OIDC token-exchange recipe.

# COMMAND ----------

# Wait for the deployed App to become ACTIVE / RUNNING.
info: dict[str, Any] = {}
for i in range(40):  # up to ~10 min
    info = w.api_client.do("GET", f"/api/2.0/apps/{config.app.name}")
    cs = (info.get("compute_status") or {}).get("state")
    aps = (info.get("app_status") or {}).get("state")
    print(f"  attempt {i+1:>2d}  compute={cs}  app={aps}")
    if cs == "ACTIVE" and aps == "RUNNING":
        break
    time.sleep(15)

app = w.apps.get(config.app.name)
print(f"\napp.url:               {app.url}")
print(f"app.oauth2_app_client_id: {app.oauth2_app_client_id}")

# COMMAND ----------

# Mint an app-scoped OAuth bearer via OIDC token-exchange.
# Subject = the notebook's runtime PAT, retrieved via the SDK's
# config/auth machinery (no dbutils plumbing).
import requests

subject_pat: str = w.config.authenticate()["Authorization"].removeprefix("Bearer ")

exchange = requests.post(
    f"{w.config.host}/oidc/v1/token",
    data={
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token": subject_pat,
        "subject_token_type": "urn:databricks:params:oauth:token-type:personal-access-token",
        "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "scope": "all-apis",
        "audience": app.oauth2_app_client_id,
    },
    timeout=30,
)
exchange.raise_for_status()
app_token: str = exchange.json()["access_token"]
print(f"Minted app-scoped bearer (len={len(app_token)})")

# COMMAND ----------

# Warm up the long-running responses tables on the deployed app.
# The wrapper auto-creates `dao_ai_responses` and
# `dao_ai_response_messages` in Lakebase on the first request --
# which can exceed gap-auth's request-timeout if it's the same
# request that does real work. Warm-up with a tiny background
# request, then proceed.
warmup = requests.post(
    f"{app.url}/v1/responses",
    headers={"Authorization": f"Bearer {app_token}", "Content-Type": "application/json"},
    json={"model": config.app.name, "input": [{"role": "user", "content": "warmup"}], "background": True},
    timeout=120,
)
print(f"[warmup] status={warmup.status_code}  body[:200]={warmup.text[:200]!r}")
warmup.raise_for_status()

# Use the OpenAI Python SDK with the app-scoped bearer.
# (Databricks ships `databricks_openai.DatabricksOpenAI` and
# `databricks_langchain.ChatDatabricks` for the same purpose, but both
# gate on `WorkspaceClient.config.oauth_token()` which is not available
# when the WC was constructed with a static OAuth bearer rather than an
# OAuth credentials strategy. The bare OpenAI client gives us the same
# surface -- pointed at the App URL -- without that gate.)
from openai import OpenAI

# OpenAI SDK appends `/responses` to base_url for `responses.create`.
# dao-ai's app exposes `/v1/responses` (and `/v1/responses/{id}`),
# so set base_url to `<app.url>/v1`.
client = OpenAI(api_key=app_token, base_url=f"{app.url.rstrip('/')}/v1")

# COMMAND ----------

# 7a -- kickoff: responses.create with background=True returns a resp_* id immediately
t0 = time.time()
kickoff = client.responses.create(
    model=config.app.name,  # ignored by dao-ai's responses agent but required by SDK
    input=[{"role": "user", "content": "Deep-research the Power Tools category for Q2 2026 and produce a thorough analyst report."}],
    background=True,
    extra_body={"custom_inputs": {"configurable": {"thread_id": f"lab15-{username}-deployed"}}},
)
deployed_resp_id: str = kickoff.id
print(f"[7a] kickoff ok: resp_id={deployed_resp_id}  status={kickoff.status}  "
      f"({int((time.time()-t0)*1000)}ms)")

# COMMAND ----------

# 7b -- retrieve: GET /v1/responses/{id} until completed
t_start = time.time()
final = kickoff
for i in range(36):  # 36 * 5s = ~3 min cap
    final = client.responses.retrieve(deployed_resp_id)
    print(f"  [7b] poll #{i+1:>2d} ({int(time.time()-t_start)}s)  status={final.status}")
    if final.status in ("completed", "failed", "cancelled"):
        break
    time.sleep(5)

if final.status == "completed" and final.output:
    last = final.output[-1]
    text = ""
    if hasattr(last, "content") and last.content:
        block = last.content[0]
        text = getattr(block, "text", "") or ""
    print(f"\n--- deployed analyst report (first 800 chars) ---\n{text[:800]}")

# COMMAND ----------

# 7c -- cancel: kickoff again, immediately cancel
cancel_kickoff = client.responses.create(
    model=config.app.name,
    input=[{"role": "user", "content": "Deep-research every category and produce a 5000-word strategic review."}],
    background=True,
    extra_body={"custom_inputs": {"configurable": {"thread_id": f"lab15-{username}-deployed-cancel"}}},
)
cancel_id: str = cancel_kickoff.id
print(f"[7c] kickoff: {cancel_id}  -- cancelling in 2s...")
time.sleep(2)

cancelled = client.responses.cancel(cancel_id)
print(f"[7c] cancelled.status: {cancelled.status}")

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
