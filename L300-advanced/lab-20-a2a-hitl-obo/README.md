# Lab 20 — A2A Protocol: HITL + OBO

**Level:** L300 (advanced)

## What you'll learn

* How dao-ai's HITL contract surfaces over A2A: a LangGraph `interrupt()` becomes a terminal `TaskStatusUpdateEvent(state=INPUT_REQUIRED)` with the interrupt payload as a `DataPart` on the status message. Clients resume by sending another `message/send` for the same `taskId` carrying `{"decisions": [...]}`.
* How dao-ai's **auto-OBO-derivation** flips the Agent Card from a single PAT/M2M `bearer` scheme to **`oauth2` + `bearer`** as soon as any resource is tagged `on_behalf_of_user: true` — no `a2a.on_behalf_of_user:` line required.
* How to use the native `a2a-sdk` client (`A2AClient.send_message`, `A2AClient.send_message_streaming`) for both the synchronous turn and the SSE-streaming variant.

## What you'll build

`a2a-hitl-<your-username>` — a single-agent dao-ai app whose `default_llm` is OBO-tagged and whose two tools (`current_time`, `say_hello`) are HITL-tagged. Every time the model calls one of them, A2A returns `state: input-required` and the lab demonstrates the resume payload.

## Pre-reqs

* dao-ai >= 0.1.80 (HITL + OBO over A2A both landed in 0.1.80).
* A workspace user identity that can deploy Databricks Apps. No service principal, no Lakebase, no Unity Catalog tables.
* **Lab 19 completed** (you've seen the basic Agent Card discovery + `message/send` round-trip).

## Steps

1. **Step 1** — install `dao-ai>=0.1.92` (which transitively brings `a2a-sdk`) + `nest-asyncio` (for notebook async).
2. **Step 2** — configure widgets.
3. **Step 3** — load `hitl_obo_agent.yaml`, compile, deploy to Apps.
4. **Step 4** — wait for the Apps proxy to come up.
5. **Step 5** — mint an app-scoped OAuth bearer (OIDC token-exchange).
6. **Step 6** — fetch the Agent Card. **Assert** it emits both `oauth2` and `bearer` schemes — proves the auto-derivation works.
7. **Step 7** — `message/send "What time is it?"` → `state: input-required`. Inspect the DataPart payload that carries the `action_requests` for `current_time_tool`.
8. **Step 8** — resume by sending another `message/send` for the same `taskId` + `contextId` carrying `{"decisions": [{"type": "approve"}]}`. The task transitions to `completed` and the artifact carries the real `current_time_tool` output.
9. **Step 9** — same flow over `A2AClient.send_message_streaming` (Server-Sent Events). Observe the lifecycle events: `submitted → working → input-required(final=True)`.

## Why both `oauth2` AND `bearer` on the Agent Card?

* `oauth2` is the **declarative auth flow** — A2A clients can read the `authorizationUrl` + `tokenUrl` + scopes and integrate the flow programmatically (no Databricks SDK required).
* `bearer` is the **wire shape** — the Apps proxy reads `Authorization: Bearer <token>` and forwards the user token via `x-forwarded-access-token` regardless of which scheme the client thought it was satisfying.

A2A's `security:` array lists both as acceptable. OAuth2-aware clients use the declarative flow; bearer-only clients pass through. Both work.

## Auto-derivation cheatsheet

| `a2a.on_behalf_of_user` | Behavior | Card emits |
|---|---|---|
| `null` (default) | Auto-derive — scan resources for any `on_behalf_of_user: true` | OBO ⇒ oauth2 + bearer, else bearer |
| `true` (explicit) | Force-advertise OBO | oauth2 + bearer |
| `false` (explicit) | Force-suppress OBO | bearer (PAT/M2M) |

## Next

* Persistent A2A task lifecycle — see `dao-ai/config/examples/20_a2a_protocol/a2a_background.yaml` for the Lakebase-backed variant (one `DatabaseModel` shared by `app.background.database`, `memory.checkpointer.database`, AND `a2a.task_store.database` — `AsyncPostgresPoolManager` dedupes by connection string so the three share a single pool).
* Custom `security_schemes` — `dao_ai.apps.a2a.security` ships ready-made constants (`BEARER_DATABRICKS_PAT`, `BEARER_DATABRICKS_M2M`, `BEARER_DATABRICKS_OBO`) and factories (`api_key_header`, `oauth2_databricks_authorization_code`, `oauth2_databricks_obo`, `openid_connect_databricks`). YAML users compose the same recipes via `${workspace.host}` substitution.
