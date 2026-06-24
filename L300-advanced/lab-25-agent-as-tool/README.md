# Lab 25 -- Agent-as-Tool: `type: app` + `type: serving_endpoint`

**Level:** L300 (advanced)

> **⚠️ Regression test — known broken in dao-ai 0.1.98.** Step 6b of the
> notebook (the `type: app` tool call from Greeter → Translator) FAILS
> today because of two real bugs in the headline 0.1.98 feature:
>
> 1. `app_agent_dispatcher.py:181` wraps the workspace client in
>    `DatabricksOpenAI(workspace_client=ws)`. Its
>    `_validate_oauth_for_apps` gate (databricks_openai
>    `clients.py:150`) requires `oauth_token()` to succeed.
> 2. When the calling agent has `on_behalf_of_user: true` on the
>    `resources.apps.<name>` reference, `workspace_client_from`
>    (`config.py:562`) builds the WC with `auth_type="pat"` from the
>    forwarded user token. PAT-auth WCs fail the OAuth gate → the
>    tool errors with `ValueError: Querying Databricks Apps requires
>    OAuth authentication`.
>
> The Translator (the leaf agent) and Step 6a (direct LLM reply) and
> 6c (`type: serving_endpoint` via Sonnet) work fine. Only Step 6b is
> blocked. When dao-ai ships the fix (either: build the OBO WC with
> an OAuth strategy so `oauth_token()` works, or use the WC's
> existing auth headers directly instead of routing through
> `DatabricksOpenAI`), this lab should pass end-to-end and graduate
> from "regression repro" to "standard L300 lab".

## Goals

- Deploy TWO dao-ai apps and wire one to call the other as a tool.
- Use the new first-class `type: app` tool kind (dao-ai 0.1.98) to delegate to a deployed Databricks App without hand-writing a factory or HTTP client.
- Use the first-class `type: serving_endpoint` tool kind side-by-side to delegate to a Model Serving endpoint (FMAPI or UC-registered agent) in the same agent.
- Verify the lazy `/agent/info` and `serving_endpoints.get().task` wire-shape discovery actually happens on the first call and is cached afterwards.

## Deliverable

A `greeter-<username>` app whose `greeter` agent has two tools:

| Tool | Type | Target |
|---|---|---|
| `translate` | `type: app` | the `translator-<username>` app deployed earlier in the same notebook |
| `fancy_rewrite` | `type: serving_endpoint` | `databricks-claude-sonnet-4-5` (FMAPI) |

You'll send three messages to the Greeter and watch the agent pick the right tool for each:

1. `"Hi"` -- no tool call, direct LLM reply.
2. `"Greet me in Spanish"` -- calls `translate` (`type: app`). Probes `/agent/info` once.
3. `"Give me a fancy welcome"` -- calls `fancy_rewrite` (`type: serving_endpoint`). Probes `serving_endpoints.get().task` once.

---

**Use case:** Two-agent delegation. The Greeter is the entry point; specialist work (translation, prose rewriting) is delegated to other deployed services. The same pattern shows up in real workloads -- a customer-support orchestrator delegating to a billing-specialist agent and a knowledge-base retrieval endpoint, for example.

**DAO-AI concept:** **First-class agent-as-tool kinds.** Prior to 0.1.98, calling another agent required `type: factory` plus one of three factory functions (`create_responses_agent_tool`, `create_chat_completions_agent_tool`, `create_agent_endpoint_tool`). Those still work, but the first-class forms are:

- Simpler -- the YAML literally says "call this app" or "call this serving endpoint."
- Type-checked at config-load time via Pydantic.
- Offline-safe -- no network calls during validation.
- Auto-discovering -- on first invocation, the dispatcher probes the target to choose the right wire shape (Responses vs Chat Completions). Set `api:` to skip the probe.

## What you'll learn

- The shape of `resources.apps:` and how `type: app` references it.
- The shape of `type: serving_endpoint` -- string sugar form (`endpoint: databricks-claude-sonnet-4-5`) and the full `InferenceEndpointModel` form (`endpoint: { name, temperature, max_tokens, ai_gateway, on_behalf_of_user }`).
- The deploy ordering trap: the Greeter references `translator-<username>` by name, so the Translator must be deployed (and `app_status: RUNNING`) **before** the Greeter is invoked. dao-ai's offline-safe design means the Greeter's config still validates without the Translator existing -- the failure mode is at first invocation, not at deploy.
- How to assert from a trace that the lazy discovery probe actually ran.

## Files

| File | Purpose |
|---|---|
| `translator.yaml` | The Translator app (Agent A). One LLM, one prompt, no tools. |
| `greeter.yaml` | The Greeter app (Agent B). One LLM, two tools (one `type: app`, one `type: serving_endpoint`). |
| `notebook.py` | Deploy both apps, mint an app-scoped bearer for the Greeter, send three inferences, inspect traces and app logs. |
| `pyproject.toml` | `dao-ai>=0.1.98`, `openai>=1.40`. |

## Prerequisites

- `databricks-claude-sonnet-4-5` foundation-model endpoint enabled (used as both the Greeter/Translator backbone LLM and the `fancy_rewrite` target).
- Workspace user identity that can deploy Databricks Apps.
- No catalog / Genie room / vector index / Lakebase needed. This lab is purely about tool wiring.

## Run

Open `notebook.py`. The notebook auto-derives `${username}` from your workspace identity, then runs end-to-end:

1. Deploy `translator.yaml` -> wait for ACTIVE.
2. Deploy `greeter.yaml` -> wait for ACTIVE.
3. Mint an app-scoped OAuth bearer for the Greeter via OIDC token-exchange.
4. Send three test prompts via the OpenAI Responses API.
5. For each response, pull the trace via `custom_outputs["trace_id"]` and verify the expected tool span appears.
6. Tail the Greeter's app logs for ERROR-level entries.

Deployed app names:

- Agent A: `translator-<your-username>`
- Agent B: `greeter-<your-username>`

Both are left running after the notebook finishes -- delete with `databricks apps delete --profile fevm <name>` when you're done.

## Migration from the legacy factory shapes

| Old shape (still works) | New first-class shape |
|---|---|
| `type: factory`, `name: dao_ai.tools.create_responses_agent_tool`, `args: { app: ..., ... }` | `type: app`, `app: <DatabricksAppModel>` |
| `type: factory`, `name: dao_ai.tools.create_chat_completions_agent_tool`, `args: { app: ..., ... }` | `type: app`, `app: <DatabricksAppModel>`, `api: completions` (force Chat Completions wire) |
| `type: factory`, `name: dao_ai.tools.create_agent_endpoint_tool`, `args: { llm: <endpoint>, ... }` | `type: serving_endpoint`, `endpoint: <name-or-InferenceEndpointModel>` |

## Next

You've seen every dao-ai first-class tool kind across the workshop:

| Kind | Lab |
|---|---|
| `unity_catalog` | 2 |
| `genie` | 3, 12 |
| `mcp` | 4 |
| `factory` (REST escape hatch) | 5 |
| `vector_search` | 6, 11 |
| `python` (HITL) | 10, 20 |
| `a2a` (server-side) | 19, 20 |
| `app` | **25** |
| `serving_endpoint` | **25** |

Return to the main workshop README for the next track.
