# Lab 2 -- Grounding with Unity Catalog Tools

**Level:** L100

## Goals

- Declare a Unity Catalog `schemas:` block with parameter-substituted `catalog_name`.
- Provision a Delta table + two UC SQL functions from DDL files via `dataset.create()` / `uc_fn.create()`.
- Wire the UC functions as `type: unity_catalog` tools and bind them to the agent.
- Watch the agent stop guessing and start calling tools for SKU and category questions.

## Deliverable

An agent that answers `"What Power Tools do you have under $100?"` by calling `find_products_by_category` and returns real catalog data.

---

**Use case:** `hardware_store` -- the greeter from chapter 1 grows into a `product_assistant` that answers SKU and category questions over a real catalog.

**dao-ai concept:** **Unity Catalog SQL functions as tools.** The agent stops guessing and starts calling typed, governed functions over a Delta table.

## What you'll learn

- The `schemas:`, `resources.functions:`, `tools:`, and `unity_catalog_functions:` YAML blocks.
- How `tools.<name>.function.type: unity_catalog` wraps a UC function as a callable tool with auto-generated typed parameters.
- The provisioning loop: `schema.create()`, `dataset.create()`, `uc_fn.create()` -- all idempotent.
- How to teach the LLM when to call which tool via the agent prompt.

## Files

| File | Purpose |
|---|---|
| `01_product_assistant.yaml` | Step 1 -- bare agent, no tools (baseline). |
| `02_product_assistant_with_sku_lookup.yaml` | Step 2 -- adds `find_product_by_sku`. |
| `03_product_assistant_with_catalog_search.yaml` | Step 3 (final / deploy) -- adds `find_products_by_category`. |
| `data/products.sql` | Seed SQL for the products table. |
| `functions/find_product_by_sku.sql`, `find_products_by_category.sql` | UC function DDL. |
| `notebook.py` | Walk through the three step files; provision once with the final config; deploy. |

## Prerequisites

- A Unity Catalog catalog you can create schemas in (workshop convention: `workshop_<your-username>`).
- `databricks-claude-sonnet-4-5` foundation-model endpoint enabled.

## Run

Open `notebook.py`. Set the `catalog` widget to your workshop catalog. The notebook provisions once with the final config, then walks through each step file in turn so you can compare the agent's behavior at each stage.

Deployed app name: `products-hw-<your-username>`.

## Next

[Chapter 3](../lab-3-genie/) -- give the agent a Genie Space so it can answer open-ended NL questions without a hand-written function for each.
