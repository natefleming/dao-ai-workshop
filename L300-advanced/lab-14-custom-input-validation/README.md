# Lab 14 -- Custom-Input Validation

**Level:** L300 (advanced)

## Goals

- Wire `dao_ai.middleware.create_custom_field_validation_middleware` into an agent so missing per-call context returns a markdown error before the model runs.
- See the difference between **required** and **optional** fields (`required: false`).
- Use validated context fields (`{store_num}`, `{customer_tier}`, `{region}`) directly inside the agent's system prompt and a UC tool's arguments.
- Watch the workflow short-circuit on a bad call vs run a real tool call on a good one.

## Deliverable

A `hardware-store-<your-username>` agent that refuses requests missing `store_num` / `customer_tier`, and -- when context is supplied -- recommends products whose price fits the customer's tier (bronze/silver/gold/platinum).

---

**Use case:** `hardware_store++` -- the Lab 2 `product_assistant` extended with per-store / per-tier customer context.

**DAO-AI concept:** Middleware-based input validation. A declarative `fields:` schema produces copy-paste-ready error messages without writing any Python.

## What you'll learn

- The `middleware:` top-level YAML block: factory + args pattern that builds a LangChain middleware on agent compile.
- How `agent.middleware: [...]` attaches a validator to an agent's pre-execution chain.
- Required vs optional field semantics — required fields short-circuit; optional fields surface in the error template but don't block.
- The runtime contract: `custom_inputs.configurable` keys flow into the validator and then into the agent's system prompt via `${var.NAME}`-style placeholders.

## Files

- `validated_advisor.yaml` -- single config with the `middleware:` block plus the standard agent / tool / app blocks.
- `notebook.py` -- install / params / provision / **three pedagogical invocations** (failure, success, required-only) / deploy.
- `data/products.sql` -- reused from Lab 2 (idempotent CREATE TABLE + INSERTs).
- `functions/find_products_by_tier.sql` -- DDL for the tier-aware UC function the agent calls.

## Prerequisites

- A Unity Catalog catalog you can write to (the `catalog` widget at the top of the notebook). The notebook auto-creates the schema and provisions every other resource via dao-ai's `.create()` SDK.
- `databricks-claude-sonnet-4-5` foundation-model endpoint enabled.
- A Databricks Apps-eligible workspace (Serverless v5).

## Run

Open `notebook.py` on Serverless compute. Set the `catalog` widget. Run cell by cell. Watch:

1. Step 6a: middleware short-circuits, you see a "Configuration Required" markdown response listing the missing fields with example values and a JSON template.
2. Step 6b: full context provided -- agent calls `find_products_by_tier` with `customer_tier=gold` and surfaces tier-fitting products.
3. Step 6c: optional `region` omitted -- agent runs successfully.
4. Step 6d: known field with unknown value -- validation passes (presence check only); agent's response handles the off-tier case in prose.

Deployed app name: `hardware-store-<your-username>`. (Same slot as Labs 1, 2, 3, 4, 11, 12, 13 -- redeploying replaces whichever lab's agent was last in the slot with this one.)

## Next

[Lab 15 -- Long-Running / Background Agents](../lab-15-long-running/) -- Responses-API kickoff/poll/cancel for slow tasks, with state persisted in Lakebase.
