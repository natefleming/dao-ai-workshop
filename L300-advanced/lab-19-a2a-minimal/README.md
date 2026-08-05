# Lab 19 — A2A Protocol (Minimal)

**Level:** L300 (advanced)

## What you'll learn

* The A2A protocol surface dao-ai auto-mounts on every Databricks Apps deployment (Agent Card + JSON-RPC `/a2a`).
* How to call those endpoints from a notebook using the **native `a2a-sdk` Python client** (`A2ACardResolver`, `A2AClient`).
* How the Agent Card auto-derives skills from your `app.agents:` list.
* The wire shape of a successful `message/send` (task lifecycle: `submitted → working → completed` with a text `Artifact`).

## What you'll build

`a2a-min-<your-username>` — a single-agent friendly-greeter deployed to Databricks Apps, exposing:

| Route | Protocol |
|---|---|
| `POST /invocations` | MLflow Responses (existing) |
| `POST /v1/responses*` | OpenAI Responses (existing) |
| **`GET /.well-known/agent-card.json`** | **A2A Agent Card discovery** |
| **`POST /a2a`** | **A2A JSON-RPC 2.0** |

All four routes share the same compiled LangGraph and the same checkpointer.

## Pre-reqs

* dao-ai >= 0.1.80 (A2A support landed in 0.1.80).
* A workspace user identity that can deploy Databricks Apps (no service principal required for this lab — the lab uses your own runtime PAT to mint an app-scoped OAuth bearer via the canonical OIDC token-exchange).

## Steps

1. **Step 1** — install `dao-ai[a2a]==0.2.4` (the `a2a` extra brings `a2a-sdk`) + `nest-asyncio` (for notebook async).
2. **Step 2** — configure widgets (username, llm_endpoint).
3. **Step 3** — load `greeter.yaml`, compile, deploy to Apps.
4. **Step 4** — wait for `compute_status == ACTIVE` and `app_status == RUNNING`.
5. **Step 5** — OIDC token-exchange to mint an app-scoped OAuth bearer (canonical pattern, same as Lab 15).
6. **Step 6** — fetch the Agent Card via `A2ACardResolver`.
7. **Step 7** — send `"say hi in 3 words"` via `A2AClient.send_message`.
8. **Step 8** — same `message/send` via raw JSON-RPC over `httpx` for comparison (so you can see the wire shape).

## What this lab does NOT cover

* HITL over A2A → **Lab 20** (`current_time` + `say_hello` tools with `human_in_the_loop:` tagging, resume via DataPart decisions).
* Lakebase-persistent task store → see `dao-ai/config/examples/20_a2a_protocol/a2a_background.yaml`.
* Server-sent-event streaming via `A2AClient.send_message_streaming` → Lab 20 covers it briefly.

## Why this matters

A2A is the open, vendor-neutral protocol for agent-to-agent collaboration (governed by the Linux Foundation). Once your dao-ai agent speaks A2A, it can be discovered + invoked by any A2A-aware client — Google's reference, the Microsoft Agent Framework, AutoGen, third-party orchestrators, etc. — without bespoke adapters.
