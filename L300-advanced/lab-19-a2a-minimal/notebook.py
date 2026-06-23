# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 19 -- A2A Protocol (Minimal)
# MAGIC
# MAGIC **Level:** L300 (advanced)
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Deploy a dao-ai agent to Databricks Apps and confirm the A2A v0.3 endpoints (`/.well-known/agent-card.json` + `POST /a2a`) auto-mount alongside the existing OpenAI Responses contract.
# MAGIC - Call those endpoints from this notebook using the **native `a2a-sdk` Python client** (`A2ACardResolver`, `A2AClient`).
# MAGIC - Inspect the Agent Card's auto-derived `skills` (one per entry in `app.agents:`) and `securitySchemes` (a single bearer scheme when no resource has OBO).
# MAGIC - See the wire shape of a `message/send` round-trip (raw JSON-RPC) for comparison.
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC A deployed `a2a-min-<your-username>` app whose Agent Card resolves to one `greeter` skill and answers `message/send` requests with a one-or-two-sentence reply.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC **DAO-AI concept:** auto-mounted `/a2a` JSON-RPC routes on every `deployment_target: apps` deployment (dao-ai 0.1.80+).
# MAGIC
# MAGIC ## Pre-reqs
# MAGIC
# MAGIC Just a workspace user identity that can deploy Databricks Apps. No service principal, no Lakebase, no Unity Catalog tables.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 -- Install dependencies
# MAGIC
# MAGIC `a2a-sdk` is Google's reference Python client for the protocol. It ships an async `A2AClient` (built on `httpx.AsyncClient`) and an `A2ACardResolver` for the well-known card discovery URL.

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.92" "nest-asyncio>=1.5"
# MAGIC # NOTE: stay on %pip, NOT %uv pip install. The %uv magic works
# MAGIC # interactively in the notebook UI but fails in the serverless v5
# MAGIC # jobs runtime (PackageNotFoundError after install completes
# MAGIC # successfully). For jobs-runtime use, the canonical alternative
# MAGIC # would be declaring deps in environments.spec.dependencies on
# MAGIC # the run/job spec.
# MAGIC %restart_python

# COMMAND ----------

from importlib.metadata import version

print(f"dao-ai  = {version('dao-ai')}")
print(f"a2a-sdk = {version('a2a-sdk')}")

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
print(f"Derived username: {username}")

dbutils.widgets.text("llm_endpoint", "databricks-gpt-5-4-mini", "LLM endpoint")

params: dict[str, str] = {
    "username": username,
    "llm_endpoint": dbutils.widgets.get("llm_endpoint").strip(),
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 -- Load, compile, deploy
# MAGIC
# MAGIC `config.deploy_agent(target=DeploymentTarget.APPS)` packages the dao-ai bundle and triggers a Databricks Asset Bundle deploy + run. The deploy job runs ~5-10 minutes; we poll the Apps API afterward in Step 4 until `compute_status == ACTIVE` and `app_status == RUNNING`.

# COMMAND ----------

from dao_ai.config import AppConfig, DeploymentTarget

config: AppConfig = AppConfig.from_file("greeter.yaml", params=params)
print(f"App name:        {config.app.name}")
print(f"Deployment:      {config.app.deployment_target}")
print(f"A2A enabled?     {config.app.a2a.enabled}")
print(f"Default scheme:  {(config.app.a2a.task_store.database is None) and 'in-memory task store' or 'Lakebase task store'}")

# COMMAND ----------

config.deploy_agent(target=DeploymentTarget.APPS)
print(f"Deployed app: {config.app.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- Wait for the Apps proxy to come up

# COMMAND ----------

info: dict[str, Any] = {}
for i in range(40):  # ~10 min cap
    info = w.api_client.do("GET", f"/api/2.0/apps/{config.app.name}")
    cs = (info.get("compute_status") or {}).get("state")
    aps = (info.get("app_status") or {}).get("state")
    print(f"  attempt {i+1:>2d}  compute={cs}  app={aps}")
    if cs == "ACTIVE" and aps == "RUNNING":
        break
    time.sleep(15)

app = w.apps.get(config.app.name)
print(f"\napp.url:                  {app.url}")
print(f"app.oauth2_app_client_id: {app.oauth2_app_client_id}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 -- Mint an app-scoped OAuth bearer
# MAGIC
# MAGIC `*.databricksapps.com` is fronted by gap-auth, which requires an audience-scoped OAuth U2M token (not a workspace runtime PAT). The canonical fix is the OIDC token-exchange endpoint: exchange the notebook's PAT for an OAuth access token whose `audience` is the App's OAuth client ID. Same pattern as Lab 15.

# COMMAND ----------

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

# MAGIC %md
# MAGIC ## Step 6 -- Fetch the Agent Card with `A2ACardResolver`
# MAGIC
# MAGIC The Agent Card is the public discovery document for an A2A agent. Clients fetch it once, then route every JSON-RPC call to its `url` field.
# MAGIC
# MAGIC dao-ai auto-derives the card from your config:
# MAGIC * **`name`** — `app.name`.
# MAGIC * **`description`** — `app.description`.
# MAGIC * **`url`** — `$DATABRICKS_APP_URL/a2a` at startup; falls back to relative `/a2a` for local dev.
# MAGIC * **`skills`** — one per entry in `app.agents:`.
# MAGIC * **`securitySchemes`** — auto-derived from OBO posture. For this lab (no resource has OBO) the card emits a single PAT/M2M bearer scheme.

# COMMAND ----------

import asyncio

import httpx
import nest_asyncio
from a2a.client import A2ACardResolver
from a2a.types import AgentCard

# Databricks notebooks run inside an active asyncio loop. nest_asyncio
# patches the loop so asyncio.run() can be called from cells without
# raising "asyncio.run() cannot be called from a running event loop".
nest_asyncio.apply()


async def fetch_agent_card() -> AgentCard:
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {app_token}"}, timeout=30) as http:
        resolver = A2ACardResolver(httpx_client=http, base_url=app.url)
        return await resolver.get_agent_card()

# Cold-start retry: even when `compute_status==ACTIVE` and
# `app_status==RUNNING`, the Apps proxy may briefly 502 on the first
# request while the inner uvicorn process finishes booting. Retry the
# first agent-card fetch; subsequent calls are fast.
card: AgentCard | None = None
last_err: Exception | None = None
for attempt in range(8):  # ~8 x 15s = 2 min cap
    try:
        card = asyncio.run(fetch_agent_card())
        break
    except Exception as e:
        last_err = e
        if any(s in str(e) for s in ("502", "Bad Gateway", "503", "504")):
            print(f"  [agent-card attempt {attempt+1}] cold start; retry in 15s")
            time.sleep(15)
        else:
            raise
if card is None:
    raise RuntimeError(f"agent card never returned 200 after retries: {last_err}")
print(f"name        : {card.name}")
print(f"description : {card.description}")
print(f"url         : {card.url}")
print(f"version     : {card.version}")
print(f"skills      : {[s.id for s in card.skills]}")
print(f"schemes     : {list((card.security_schemes or {}).keys())}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 -- Send a message via `A2AClient.send_message`
# MAGIC
# MAGIC The native client takes:
# MAGIC * an `httpx.AsyncClient` (we reuse the one carrying the bearer),
# MAGIC * the resolved `AgentCard`,
# MAGIC * and dispatches `SendMessageRequest` (`message/send`) to the card's `url` over JSON-RPC.
# MAGIC
# MAGIC On a happy-path single-turn agent, the `Task` lifecycle goes `submitted → working → completed`, and the response carries a text `Artifact` with the model's reply.

# COMMAND ----------

import uuid

from a2a.client import A2AClient
from a2a.types import (
    Message,
    MessageSendParams,
    SendMessageRequest,
    SendMessageResponse,
    Task,
    TextPart,
)


async def send_one_message(text: str) -> SendMessageResponse:
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {app_token}"}, timeout=60) as http:
        client = A2AClient(httpx_client=http, agent_card=card)
        request = SendMessageRequest(
            id=uuid.uuid4().hex[:8],
            params=MessageSendParams(
                message=Message(
                    message_id=uuid.uuid4().hex,
                    role="user",
                    parts=[TextPart(text=text)],
                )
            ),
        )
        return await client.send_message(request)


resp: SendMessageResponse = asyncio.run(send_one_message("Say hi in 3 words."))
# `.root` is a SendMessageSuccessResponse (carrying a Task or Message) or
# a JSONRPCErrorResponse. Happy-path of a single-shot greeter agent: Task.
assert isinstance(resp.root.result, Task), f"expected Task, got {type(resp.root.result).__name__}"
result: Task = resp.root.result
print(f"task_id   : {result.id}")
print(f"contextId : {result.context_id}")
print(f"state     : {result.status.state}")
artifact_text: str = ""
if result.artifacts:
    first_part = result.artifacts[0].parts[0].root
    if isinstance(first_part, TextPart):
        artifact_text = first_part.text
print(f"reply     : {artifact_text!r}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 8 -- Same `message/send` via raw JSON-RPC (for comparison)
# MAGIC
# MAGIC The native client builds these payloads for you. Seeing the wire shape once helps when debugging interop with non-Python A2A clients (Java, Go, etc.). The native client is the recommended interface for production use.

# COMMAND ----------

import json

rpc_body = {
    "jsonrpc": "2.0",
    "id": uuid.uuid4().hex[:8],
    "method": "message/send",
    "params": {
        "message": {
            "messageId": uuid.uuid4().hex,
            "role": "user",
            "parts": [{"kind": "text", "text": "Say hi in 3 words."}],
        }
    },
}
raw = requests.post(
    f"{app.url}/a2a",
    headers={"Authorization": f"Bearer {app_token}", "Content-Type": "application/json"},
    json=rpc_body,
    timeout=60,
)
raw.raise_for_status()
envelope = raw.json()
print(f"task_id   : {envelope['result']['id']}")
print(f"state     : {envelope['result']['status']['state']}")
text = ""
artifacts = envelope["result"].get("artifacts") or []
if artifacts:
    text = artifacts[0]["parts"][0].get("text", "")
print(f"reply     : {text!r}")
print()
print("--- raw envelope (truncated) ---")
print(json.dumps(envelope, indent=2)[:800])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next
# MAGIC
# MAGIC **Lab 20** adds the two interesting wrinkles that turn A2A into a real production protocol:
# MAGIC
# MAGIC 1. **HITL** — tools tagged `human_in_the_loop:` interrupt the graph mid-execution. The A2A executor returns `state: input-required` with the interrupt payload as a `DataPart` on the status message. The caller resumes by sending another `message/send` with the same `taskId` + `contextId` carrying `{"decisions": [...]}`.
# MAGIC 2. **OBO** — when any resource has `on_behalf_of_user: true`, the Agent Card auto-promotes to **`oauth2` + `bearer`** schemes with the real workspace OIDC URLs and a `user_impersonation` scope, so A2A clients know the deployment honors user-token forwarding.
# MAGIC
# MAGIC Lab 20 also shows `A2AClient.send_message_streaming` (server-sent events for the same task).
