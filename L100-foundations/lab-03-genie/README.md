# Lab 3 -- NL Analytics with Genie

**Level:** L100

## Goals

- Add a `genie_rooms:` resource pointing at a Databricks Genie Space.
- Wrap the room as a `factory` tool via `dao_ai.tools.create_genie_tool`.
- See the agent delegate open-ended analytical questions to Genie instead of needing a hand-written UC function.

## Deliverable

An `analyst` agent that answers `"How many products do we have per category?"` by calling Genie and summarising the result.

---

**Use case:** `hardware_store` -- the `product_assistant` from lab 2 promotes to an `analyst` that answers ad-hoc analytical questions via Databricks Genie.

**DAO-AI concept:** **Genie Space as a factory tool.** Instead of writing a UC function for every analytical question, point the agent at a Genie Space and let Genie generate the SQL on the fly.

## What you'll learn

- The `resources.genie_rooms:` block and the `factory` tool type.
- How `dao_ai.tools.create_genie_tool` wraps a Genie Space as a callable.
- When Genie wins (open-ended analytics, broad schema) vs. when UC functions win (latency, determinism, audit).

## Files

| File | Purpose |
|---|---|
| `analyst.yaml` | The agent config -- one LLM, one Genie tool. |
| `notebook.py` | Walk through the config, test, deploy. |

## Prerequisites

- Lab 2 run -- the `products` table must exist.
- A **Genie Space** created manually in the Databricks UI, pointed at the `products` table. Copy its space ID.
- `databricks-claude-sonnet-4-5` foundation-model endpoint enabled.

## Run

Open `notebook.py`. Set the `genie_space_id` widget to the ID you copied. The notebook builds the agent and asks an analytical question that would have required a new UC function in lab 2.

Deployed app name: `hardware-store-<your-username>`.

## Next

[Lab 4](../lab-04-mcp/) -- replace per-function tool declarations with **managed MCP** auto-discovery over the entire schema.
