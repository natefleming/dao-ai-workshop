# Lab 15 -- Long-Running / Background Agents

**Level:** L300 (advanced)

## Goals

- Configure `app.long_running:` so dao-ai wraps the agent with `LongRunningResponsesAgent`, persisting kickoff state in Lakebase.
- Hit the Responses-API surface on the **deployed Databricks App** (`/invocations` + `/v1/responses/{id}`) using `WorkspaceClient` to authenticate and `requests` to call out — the way a real client process would.
- Understand why long-running agents need a checkpointer (state has to survive across kickoff/poll turns), and why the long-running contract is a deployed-endpoint contract (the responses tables are owned by the deployed app's service principal).

## Deliverable

A `hardware-store-<your-username>` agent that, when called with `background: true` against the deployed app, returns a `resp_*` ID immediately and produces a multi-paragraph inventory analysis ~30-90 seconds later — retrievable via `GET /v1/responses/{id}`.

---

**Use case:** `hardware_store++` — inventory analyst agent that produces deep-research style reports.

**DAO-AI concept:** `app.long_running:` block + `LongRunningResponsesAgent` wrapper + Lakebase-backed responses store.

## What you'll learn

- How `app.long_running:` toggles the LongRunningResponsesAgent wrapper.
- The Responses-API runtime contract (`background: true` / `GET /v1/responses/{id}` / `operation: "cancel"`).
- Why background work needs a checkpointer (Lab 7 introduced this; here we reuse the same Lakebase wiring).
- Why long-running is a **deployed-endpoint contract**: the responses tables are owned by the app's service principal, so an in-notebook predict against the same Lakebase would hit `InsufficientPrivilege` -- exercise the contract over HTTP instead.
- How a real client (e.g. a non-notebook backend) authenticates using `WorkspaceClient` + `Authorization: Bearer <token>` and calls the deployed app.
- Why this lab sets `enable_chat_proxy: false` -- the long-running pattern is a headless API contract, so we skip the chat-UI build and let FastAPI bind directly to the platform's expected port.

## Files

- `background_advisor.yaml` — single config with `resources.databases:` (Lakebase) + `memory.checkpointer:` + `app.long_running:` + `enable_chat_proxy: false`.
- `notebook.py` — install / params / provision Lakebase role / compile / deploy / **post-deploy kickoff + retrieve + cancel via HTTP using `WorkspaceClient`**.

## Prerequisites

Same Lakebase / SP setup Lab 7 needs:

- `setup/create_service_principal.py` (creates the `dao-ai-workshop-sp` SP and the `dao_ai_workshop` secret scope with `DAO_AI_SP_CLIENT_ID` + `DAO_AI_SP_CLIENT_SECRET`).
- `setup/grant_lakebase_superuser.py` (grants the SP `DATABRICKS_SUPERUSER` on the Lakebase project so the long-running wrapper can create its tables).
- The `retail-consumer-goods` Lakebase autoscaling project must exist in the workspace.

## Run

Open `notebook.py` on Serverless compute. Run cell by cell. Watch:

1. **Step 3 (provision Lakebase role)** — `database.create()` creates the SP's postgres `DATABRICKS_SUPERUSER` role (idempotent, same pattern as Lab 7). The `dao_ai_responses` / `dao_ai_response_messages` tables are auto-created by the long-running wrapper on first request.
2. **Step 5 (compile)** — confirms the wrapped class is `LongRunningResponsesAgent`. We do not exercise the contract in-process: the responses tables are owned by the deployed app's SP, so an in-notebook predict (under the user's PAT) would hit `InsufficientPrivilege`.
3. **Step 6 (deploy)** — pushes the agent to a Databricks App. First deploy is ~3-5 min for compute warm-up.
4. **Step 7 polling loop** waits for `compute_status: ACTIVE` + `app_status: RUNNING`.
5. **Step 7a (kickoff)** — `WorkspaceClient` mints a bearer token, `requests.post` to `<app_url>/invocations` with `"background": true`. Returns within ~1s with `status: in_progress` and a `resp_*` id.
6. **Step 7b (retrieve)** — `requests.get` to `<app_url>/v1/responses/<resp_id>` polls every 5s until `completed`. ~30-90s wallclock for the analyst report.
7. **Step 7c (cancel)** — second kickoff, immediate cancel via `operation: cancel`, status flips to `cancelled`.

Deployed app name: `hardware-store-<your-username>`. (Same slot as Labs 1, 2, 3, 4, 11, 12, 13, 14 — redeploying replaces whichever lab's agent was last in the slot with this one.)

## Next

You've now seen every L300 pattern: instructed retrieval (Lab 11), Genie caching (Lab 12), programmatic construction (Lab 13), custom-input validation (Lab 14), and long-running agents (Lab 15). Re-read the L300 README's "what's next" section for production-deployment guidance.
