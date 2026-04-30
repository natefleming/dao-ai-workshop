# Lab 15 -- Long-Running / Background Agents

**Level:** L300 (advanced)

## Goals

- Configure `app.long_running:` so dao-ai wraps the agent with `LongRunningResponsesAgent`, persisting kickoff state in Lakebase.
- Exercise the Responses-API contract end-to-end **inside the notebook**: kickoff (`background: true`), retrieve (`operation: "retrieve"`), cancel (`operation: "cancel"`).
- Hit the **same surface on the deployed Databricks App** (`/invocations` + `/v1/responses/{id}`) using `WorkspaceClient` to authenticate and `requests` to call out — the way a real client process would.
- Understand why long-running agents need a checkpointer (state has to survive across kickoff/poll turns).

## Deliverable

A `hardware-store-<your-username>` agent that, when called with `background: true`, returns a `resp_*` ID immediately and produces a multi-paragraph inventory analysis ~30-90 seconds later — retrievable by ID either in-notebook (`predict({...operation: retrieve...})`) or against the deployed app (`GET /v1/responses/{id}`).

---

**Use case:** `hardware_store++` — inventory analyst agent that produces deep-research style reports.

**DAO-AI concept:** `app.long_running:` block + `LongRunningResponsesAgent` wrapper + Lakebase-backed responses store.

## What you'll learn

- How `app.long_running:` toggles the LongRunningResponsesAgent wrapper.
- The Responses-API runtime contract (`background: true` / `operation: "retrieve"` / `operation: "cancel"`).
- Why background work needs a checkpointer (Lab 7 introduced this; here we reuse the same Lakebase wiring).
- The two equivalent ways to retrieve a long-running result: `custom_inputs.operation: "retrieve"` on `/invocations`, or the strict OpenAI-style `/v1/responses/{id}` route on the deployed app.
- How a real client (e.g. a non-notebook backend) authenticates using `WorkspaceClient` + `Authorization: Bearer <token>` and calls the deployed app.

## Files

- `background_advisor.yaml` — single config with `resources.databases:` (Lakebase) + `memory.checkpointer:` + `app.long_running:`.
- `notebook.py` — install / params / provision Lakebase role / kickoff / poll / cancel / deploy / **post-deploy WorkspaceClient inference**.

## Prerequisites

Same Lakebase / SP setup Lab 7 needs:

- `setup/create_service_principal.sh` (creates the `dao-ai-workshop-sp` SP and the `dao_ai_workshop` secret scope with `DAO_AI_SP_CLIENT_ID` + `DAO_AI_SP_CLIENT_SECRET`).
- `setup/grant_lakebase_superuser.sh` (grants the SP `DATABRICKS_SUPERUSER` on the Lakebase project so the long-running wrapper can create its tables).
- The `retail-consumer-goods` Lakebase autoscaling project must exist in the workspace.

## Run

Open `notebook.py` on Serverless compute. Run cell by cell. Watch:

1. **Step 6a (kickoff)** — `process_messages(...)` returns within ~1s with `status: in_progress` and a `resp_*` id.
2. **Step 6b (retrieve)** — repeated `operation: "retrieve"` calls show `in_progress` for ~30-90s, then `completed` with a multi-paragraph analyst report.
3. **Step 6c (cancel)** — second kickoff, immediate cancel, status flips to `cancelled`.
4. **Step 7 deploy** — pushes the same agent to a Databricks App.
5. **Step 8** waits for compute / app to be ACTIVE / RUNNING.
6. **Step 9** — `WorkspaceClient` mints a bearer token, `requests.post` to `<app_url>/invocations` with `background: true`, then poll `<app_url>/v1/responses/<resp_id>` until `completed`.

The first deploy may take a couple of minutes for compute to come up; expect ~3-5 min wallclock for Step 8 the first time.

Deployed app name: `hardware-store-<your-username>`. (Same slot as Labs 1, 2, 3, 4, 11, 12, 13, 14 — redeploying replaces whichever lab's agent was last in the slot with this one.)

## Next

You've now seen every L300 pattern: instructed retrieval (Lab 11), Genie caching (Lab 12), programmatic construction (Lab 13), custom-input validation (Lab 14), and long-running agents (Lab 15). Re-read the L300 README's "what's next" section for production-deployment guidance.
