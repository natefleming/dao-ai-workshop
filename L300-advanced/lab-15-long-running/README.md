# Lab 15 -- Long-Running / Background Agents

**Level:** L300 (advanced)

## Goals

- Configure `app.long_running:` so dao-ai wraps the agent with `LongRunningResponsesAgent`, persisting kickoff state in Lakebase.
- Invoke the deployed **Databricks App** from a notebook using the canonical SDK-clean pattern: OIDC token-exchange (`POST /oidc/v1/token`, audience = `app.oauth2_app_client_id`) to mint an app-scoped OAuth bearer, then the bare **OpenAI Python SDK** pointed at `<app.url>/v1` for `responses.create / .retrieve / .cancel`.
- Understand why long-running agents need a checkpointer (state has to survive across kickoff/poll turns) and why the contract is a deployed-endpoint contract (the responses tables are owned by the deployed app's SP, so an in-notebook predict under the user's PAT would hit `InsufficientPrivilege`).

## Deliverable

A `hardware-store-<your-username>` agent that, when called with `background=True` via `client.responses.create(...)`, returns a `resp_*` ID immediately and produces a multi-paragraph inventory analysis ~30-90 seconds later — retrievable via `client.responses.retrieve(id)`, cancellable via `client.responses.cancel(id)`.

---

**Use case:** `hardware_store++` — inventory analyst agent that produces deep-research style reports.

**DAO-AI concept:** `app.long_running:` block + `LongRunningResponsesAgent` wrapper + Lakebase-backed responses store.

## What you'll learn

- How `app.long_running:` toggles the `LongRunningResponsesAgent` wrapper.
- The Responses-API runtime contract: `background=True` kickoff, `responses.retrieve(id)` poll, `responses.cancel(id)`.
- Why background work needs a checkpointer (Lab 7 introduced this; here we reuse the same Lakebase wiring).
- Why long-running is a **deployed-endpoint contract**: the responses tables are owned by the deployed app's SP, so an in-notebook predict against the same Lakebase would hit `InsufficientPrivilege` -- always exercise the contract via the deployed App URL.
- The canonical Apps-invocation auth dance from a notebook: a workspace runtime PAT does **not** satisfy the Apps gap-auth proxy, so the lab exchanges it via `POST /oidc/v1/token` (audience = `app.oauth2_app_client_id`) for an app-scoped OAuth bearer.
- Why we use the **bare OpenAI Python SDK** instead of `databricks_openai.DatabricksOpenAI` or `databricks_langchain.ChatDatabricks`: those clients gate on `WorkspaceClient.config.oauth_token()` and reject WCs constructed from a static OAuth bearer. The bare client gives us the same `responses.*` surface with no gate.
- Why this lab sets `enable_chat_proxy: false` -- the long-running pattern is a headless API contract, no chat UI needed.
- Why this lab scopes the Lakebase response table names per-user (`dao_ai_responses_<username_sql>`): default names collide across students because every deployed app's SP owns its tables, and orphaned SP roles can't be cleaned up from outside the control plane.

## Files

- `background_advisor.yaml` — single config with `resources.databases:` (Lakebase) + `memory.checkpointer:` + `app.long_running:` (with per-user `responses_table_name` / `messages_table_name`) + `enable_chat_proxy: false`.
- `notebook.py` — install / params / provision Lakebase role / compile / deploy / OIDC token-exchange + warm-up / **kickoff + retrieve + cancel via the OpenAI SDK**.

## Prerequisites

Same Lakebase / SP setup Lab 7 needs:

- `setup/create_service_principal.py` (creates the `dao-ai-workshop-sp` SP and the `dao_ai_workshop` secret scope with `DAO_AI_SP_CLIENT_ID` + `DAO_AI_SP_CLIENT_SECRET`).
- `setup/grant_lakebase_superuser.py` (grants the SP `DATABRICKS_SUPERUSER` on the Lakebase project so the long-running wrapper can create its tables).
- The `retail-consumer-goods` Lakebase autoscaling project must exist in the workspace.

## Run

Open `notebook.py` on Serverless compute. Run cell by cell. Watch:

1. **Step 3 (provision Lakebase role)** — `database.create()` creates the SP's postgres `DATABRICKS_SUPERUSER` role (idempotent, same pattern as Lab 7). The per-user `dao_ai_responses_<username_sql>` / `dao_ai_response_messages_<username_sql>` tables are auto-created by the long-running wrapper on first request.
2. **Step 5 (compile)** — confirms the wrapped class is `LongRunningResponsesAgent`. We do not exercise the contract in-process: the responses tables are owned by the deployed app's SP, so an in-notebook predict (under the user's PAT) would hit `InsufficientPrivilege`.
3. **Step 6 (deploy)** — pushes the agent to a Databricks App. First deploy is ~3-5 min for compute warm-up.
4. **Step 7 polling loop** waits for `compute_status: ACTIVE` + `app_status: RUNNING`, then fetches `app.url` and `app.oauth2_app_client_id`.
5. **Step 7 token exchange** — `POST <host>/oidc/v1/token` with the notebook's runtime PAT as `subject_token` and `app.oauth2_app_client_id` as `audience`. Returns an app-scoped OAuth bearer that satisfies gap-auth.
6. **Step 7 warm-up** — a tiny `requests.post` to `<app.url>/v1/responses` so the wrapper's first-request DDL (creating the response tables) finishes before the SDK call hits gap-auth's request-timeout.
7. **Step 7a (kickoff)** — `client.responses.create(model=..., background=True, ...)` returns within ~1s with `status="in_progress"` and a `resp_*` id.
8. **Step 7b (retrieve)** — `client.responses.retrieve(id)` polls every 5s until `completed`. ~30-90s wallclock for the analyst report.
9. **Step 7c (cancel)** — second kickoff, immediate `client.responses.cancel(id)`, `status` flips to `cancelled`.

Deployed app name: `hardware-store-<your-username>`. (Same slot as Labs 1, 2, 3, 4, 11, 12, 13, 14 — redeploying replaces whichever lab's agent was last in the slot with this one.)

## Next

You've now seen every L300 pattern: instructed retrieval (Lab 11), Genie caching (Lab 12), programmatic construction (Lab 13), custom-input validation (Lab 14), and long-running agents (Lab 15). Re-read the L300 README's "what's next" section for production-deployment guidance.
