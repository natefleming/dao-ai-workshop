# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 20 -- A2A Protocol: HITL + OBO
# MAGIC
# MAGIC **Level:** L300 (advanced)
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - See dao-ai's HITL contract surface over A2A: a LangGraph `interrupt()` becomes `state: input-required` plus a DataPart payload on the task's status message; resume by sending another `message/send` for the same `taskId` + `contextId` carrying `{"decisions": [...]}`.
# MAGIC - Confirm dao-ai's **auto-OBO-derivation**: when ANY resource has `on_behalf_of_user: true`, the Agent Card auto-promotes from a single PAT/M2M `bearer` scheme to **`oauth2` + `bearer`** -- including real `authorizationUrl`/`tokenUrl` from the current workspace, and a `user_impersonation` scope.
# MAGIC - Exercise the native `a2a-sdk` client for both the synchronous (`A2AClient.send_message`) and the SSE-streaming (`A2AClient.send_message_streaming`) paths.
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC A deployed `a2a-hitl-<your-username>` app whose Agent Card carries both `oauth2` and `bearer` schemes, and which round-trips a HITL interrupt + resume over A2A using the native client.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC **DAO-AI concepts:**
# MAGIC * `tools.<x>.function.human_in_the_loop:` — flips the LangGraph subgraph to pause on tool call.
# MAGIC * `resources.models.<x>.on_behalf_of_user: true` — routes that model's invocations through the calling user's forwarded bearer.
# MAGIC * `app.a2a.on_behalf_of_user` (three-state, `Optional[bool] = None`) — `null` auto-derives from resources.
# MAGIC
# MAGIC ## Pre-reqs
# MAGIC
# MAGIC Workshop pre-reqs only. No service principal, no Lakebase, no UC tables. Complete Lab 19 first.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 -- Install dependencies

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.98" "nest-asyncio>=1.5"
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
# MAGIC Confirm before deploy: the YAML has `default_llm.on_behalf_of_user: true` but no `app.a2a.on_behalf_of_user:` line. dao-ai's auto-derivation will flip the Agent Card to both schemes.

# COMMAND ----------

from dao_ai.config import AppConfig, DeploymentTarget

config: AppConfig = AppConfig.from_file("hitl_obo_agent.yaml", params=params)
print(f"App name:                 {config.app.name}")
print(f"Deployment target:        {config.app.deployment_target}")
print(f"a2a.enabled:              {config.app.a2a.enabled}")
print(f"a2a.on_behalf_of_user:    {config.app.a2a.on_behalf_of_user}  (None => auto-derive)")
# Inspect the OBO posture across resources:
for name, m in (config.resources.models or {}).items():
    print(f"  resource.model[{name}].on_behalf_of_user = {m.on_behalf_of_user}")

# COMMAND ----------

config.deploy_agent(target=DeploymentTarget.APPS)
print(f"Deployed app: {config.app.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- Wait for the Apps proxy

# COMMAND ----------

info: dict[str, Any] = {}
for i in range(40):
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
# MAGIC ## Step 6 -- Fetch the Agent Card and assert auto-OBO-derivation
# MAGIC
# MAGIC The Agent Card should now carry BOTH schemes:
# MAGIC * `bearer` -- with an "OBO supported" description.
# MAGIC * `oauth2` -- with the workspace's real `oidc/v1/authorize` + `oidc/v1/token` URLs and the `user_impersonation` scope.

# COMMAND ----------

import asyncio

import httpx
import nest_asyncio
from a2a.client import A2ACardResolver
from a2a.types import AgentCard, OAuth2SecurityScheme

# Databricks notebooks run inside an active asyncio loop. nest_asyncio
# patches the loop so asyncio.run() can be called from cells without
# raising "asyncio.run() cannot be called from a running event loop".
nest_asyncio.apply()


async def fetch_card() -> AgentCard:
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {app_token}"}, timeout=30) as http:
        return await A2ACardResolver(httpx_client=http, base_url=app.url).get_agent_card()

# Cold-start retry: the Apps proxy may briefly 502 on the first request
# while the inner uvicorn process finishes booting.
card: AgentCard | None = None
last_err: Exception | None = None
for attempt in range(8):  # ~8 x 15s = 2 min cap
    try:
        card = asyncio.run(fetch_card())
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
print(f"skills          : {[s.id for s in card.skills]}")
scheme_names = list((card.security_schemes or {}).keys())
print(f"securitySchemes : {scheme_names}")

# Assertion: auto-derivation should have flipped both schemes on.
assert "bearer" in scheme_names, f"expected bearer scheme, got {scheme_names}"
assert "oauth2" in scheme_names, (
    f"expected oauth2 scheme (auto-derived from resource OBO), got {scheme_names}. "
    "Check that default_llm.on_behalf_of_user=true in the YAML."
)
oauth2_root = card.security_schemes["oauth2"].root
assert isinstance(oauth2_root, OAuth2SecurityScheme), (
    f"expected OAuth2SecurityScheme, got {type(oauth2_root).__name__}"
)
flow = oauth2_root.flows.authorization_code
assert flow is not None, "expected an authorizationCode flow on the OAuth2 scheme"
print()
print(f"oauth2.authorization_url : {flow.authorization_url}")
print(f"oauth2.token_url         : {flow.token_url}")
print(f"oauth2.scopes            : {flow.scopes}")
assert "user_impersonation" in flow.scopes
print("\n✓ Agent Card auto-derived OBO advertisement is correct.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 -- `message/send` -> `input-required`
# MAGIC
# MAGIC The model decides to call `current_time_tool`. The tool is HITL-tagged, so the LangGraph executor pauses and dao-ai returns a `Task` with `state: input-required`. The status message carries a DataPart with the interrupt's `action_requests` + `review_configs`.

# COMMAND ----------

import uuid

from a2a.client import A2AClient
from a2a.types import (
    DataPart,
    Message,
    MessageSendParams,
    SendMessageRequest,
    SendMessageResponse,
    Task,
    TextPart,
)


async def send_initial() -> SendMessageResponse:
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {app_token}"}, timeout=60) as http:
        client = A2AClient(httpx_client=http, agent_card=card)
        request = SendMessageRequest(
            id=uuid.uuid4().hex[:8],
            params=MessageSendParams(
                message=Message(
                    message_id=uuid.uuid4().hex,
                    role="user",
                    parts=[TextPart(text="What time is it?")],
                ),
            ),
        )
        return await client.send_message(request)


resp1: SendMessageResponse = asyncio.run(send_initial())
assert isinstance(resp1.root.result, Task), f"expected Task, got {type(resp1.root.result).__name__}"
task: Task = resp1.root.result
print(f"task_id     : {task.id}")
print(f"context_id  : {task.context_id}")
print(f"state       : {task.status.state}")

# Inspect the HITL DataPart on the status message.
status_msg: Message | None = task.status.message
if status_msg is not None:
    data_parts: list[DataPart] = [
        p.root for p in (status_msg.parts or []) if isinstance(p.root, DataPart)
    ]
    if data_parts:
        interrupts = data_parts[0].data.get("interrupts", [])
        if interrupts:
            ar: dict = interrupts[0]["value"]["action_requests"][0]
            print(f"\nHITL interrupt: tool={ar['name']!r}, args={ar.get('args', {})}")
            print(f"  review_prompt (first 80 chars): {ar.get('description', '')[:80]!r}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 8 -- Resume with a DataPart decision
# MAGIC
# MAGIC The structured-resume contract: a `DataPart` on the same `taskId` + `contextId` carrying `{"decisions": [{"type": "approve"}]}` lets dao-ai bypass the LLM parser entirely. This is the canonical machine-to-machine resume shape.

# COMMAND ----------

task_id: str = task.id
context_id: str = task.context_id


async def resume_with_approve() -> SendMessageResponse:
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {app_token}"}, timeout=60) as http:
        client = A2AClient(httpx_client=http, agent_card=card)
        request = SendMessageRequest(
            id=uuid.uuid4().hex[:8],
            params=MessageSendParams(
                message=Message(
                    message_id=uuid.uuid4().hex,
                    task_id=task_id,
                    context_id=context_id,
                    role="user",
                    parts=[DataPart(data={"decisions": [{"type": "approve"}]})],
                ),
            ),
        )
        return await client.send_message(request)


resp2: SendMessageResponse = asyncio.run(resume_with_approve())
assert isinstance(resp2.root.result, Task), f"expected Task, got {type(resp2.root.result).__name__}"
result2: Task = resp2.root.result
print(f"state    : {result2.status.state}")
artifact_text: str = ""
if result2.artifacts:
    first_part = result2.artifacts[0].parts[0].root
    if isinstance(first_part, TextPart):
        artifact_text = first_part.text
print(f"artifact : {artifact_text!r}")
assert result2.status.state == "completed", f"expected completed, got {result2.status.state}"
print("\n✓ HITL resume completed end-to-end over A2A.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 9 -- Streaming variant (`A2AClient.send_message_streaming`)
# MAGIC
# MAGIC The same `message/send` shape, but over the JSON-RPC streaming endpoint. dao-ai emits one Server-Sent Event per state transition. For a HITL flow, you'll see `submitted -> working -> input-required(final=True)` and the stream closes -- there's no "wait and then resume" within a single stream; the client opens a fresh stream after sending the resume `DataPart`.

# COMMAND ----------

from a2a.types import (
    SendStreamingMessageRequest,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)


async def stream_initial() -> list[str]:
    events: list[str] = []
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {app_token}"}, timeout=60) as http:
        client = A2AClient(httpx_client=http, agent_card=card)
        request = SendStreamingMessageRequest(
            id=uuid.uuid4().hex[:8],
            params=MessageSendParams(
                message=Message(
                    message_id=uuid.uuid4().hex,
                    role="user",
                    parts=[TextPart(text="Say hello to the team.")],
                ),
            ),
        )
        async for event in client.send_message_streaming(request):
            root = event.root.result
            label = type(root).__name__
            # The streaming union is Task | Message | TaskStatusUpdateEvent |
            # TaskArtifactUpdateEvent. Each has its own shape; dispatch on
            # the concrete type so each branch reads typed attributes.
            if isinstance(root, TaskStatusUpdateEvent):
                events.append(f"{label}:{root.status.state}(final={root.final})")
            elif isinstance(root, TaskArtifactUpdateEvent):
                events.append(f"{label}:artifact(last_chunk={root.last_chunk})")
            elif isinstance(root, Task):
                events.append(f"{label}:{root.status.state}")
            elif isinstance(root, Message):
                events.append(f"{label}:message(role={root.role})")
            else:
                events.append(f"{label}:unknown")
    return events


stream_events: list[str] = asyncio.run(stream_initial())
for e in stream_events:
    print(f"  {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next
# MAGIC
# MAGIC You've now seen the full A2A surface dao-ai exposes:
# MAGIC
# MAGIC | Capability | Lab |
# MAGIC |---|---|
# MAGIC | Agent Card discovery + `message/send` | Lab 19 |
# MAGIC | HITL `input-required` + DataPart resume | Lab 20 (this) |
# MAGIC | Auto-derived `oauth2 + bearer` from resource OBO | Lab 20 (this) |
# MAGIC | SSE streaming via `send_message_streaming` | Lab 20 (this) |
# MAGIC | Lakebase-persistent task store + `tasks/get` round-trip | `dao-ai/config/examples/20_a2a_protocol/a2a_background.yaml` |
# MAGIC
# MAGIC The L300 README's "what's next" section covers production hardening (security scheme overrides via `dao_ai.apps.a2a.security`, custom skills, Lakebase task persistence).
