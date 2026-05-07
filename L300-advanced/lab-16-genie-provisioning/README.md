# Lab 16 -- Declarative Genie Space Provisioning

**Level:** L300

## Goals

- Provision a fully-configured Genie space declaratively from a single YAML config.
- Exercise every `GenieRoomModel` capability: table sources with column configs, metric view sources, function sources, text instructions, example SQLs (with parameters), SQL snippets (filters / expressions / measures), sample questions, benchmarks, and entitlements.
- Understand how `datasets:` + `unity_catalog_functions:` + `resources.genie_rooms:` chain into a single `.create()` provisioning pipeline.

## Deliverable

A Genie Space named `Workshop Provisioned Genie (<your-username>)` backed by two tables, two views, and two UC SQL functions -- with the full suite of Genie instructions, snippets, benchmarks, and permissions applied.

---

**Use case:** `hardware_store` -- the same products/orders domain from L100, but here we provision the Genie space itself rather than consuming an existing one.

**DAO-AI concept:** **Declarative resource provisioning.** Instead of creating a Genie Space in the UI, define the full space configuration in YAML and run `GenieRoomModel.create()` to provision it programmatically. No `agents:`, no `app:` -- just resources.

## What you'll learn

- The full `GenieRoomModel` object model and every configurable field.
- How `DatasetModel.create()` and `UnityCatalogFunctionSqlModel.create()` provision UC objects from SQL files.
- How `GenieRoomModel.create()` translates YAML into the Genie API's `serialized_space` payload.
- The relationship between `resources.tables` / `resources.functions` anchors and `table_sources` / `function_sources` references inside the Genie room.

## Files

| File | Purpose |
|---|---|
| `genie_room.yaml` | The full config -- schemas, resources, datasets, UC functions, and a Genie room exercising every field. |
| `notebook.py` | Walk through each provisioning step: schemas, datasets, UC functions, Genie space. |
| `data/products.sql` | DDL + seed data for the `products` table (30 rows, includes `status` and `internal_notes` columns). |
| `data/orders.sql` | DDL + seed data for the `orders` table (30 rows). |
| `data/active_products_v.sql` | DDL for the `active_products_v` view (filters to `status = 'ACTIVE'`). |
| `data/daily_sales_mv.sql` | DDL for the `daily_sales_mv` view (daily sales aggregation by category). |
| `functions/find_product_by_sku.sql` | UC SQL function: look up products by SKU array. |
| `functions/find_orders_in_date_range.sql` | UC SQL function: return orders within a date range. |

## Prerequisites

- A Unity Catalog catalog where you have `CREATE` privileges.
- A **SQL warehouse** -- copy its ID from the warehouse detail page.
- A **workspace folder** for `parent_path` where the Genie space will be created (e.g., `/Users/you@databricks.com/genie`).
- `databricks-claude-sonnet-4-5` is **not** required -- this lab provisions resources only and does not run an agent.
- The `entitlements` in the YAML reference the groups `users` and `admins`. Edit these to match real groups in your workspace, or remove the `entitlements` block if you don't need permissions applied.

## Run

Open `notebook.py`. Set the four widgets:

| Widget | Example |
|---|---|
| `catalog` | `workshop_jane_doe` |
| `schema` | `dao_ai` |
| `warehouse_id` | `abc123def456` |
| `genie_parent_path` | `/Users/jane.doe@databricks.com/genie` |

Run all cells. The notebook provisions schemas, tables, views, UC functions, and then the Genie space. After provisioning, it demonstrates `GenieRoomModel.from_space(space_id)` to reconstruct a fully-hydrated model from the live space -- useful for exporting, diffing, or cloning spaces programmatically.

## After provisioning

Pass the printed `space_id` to [Lab 3 -- NL Analytics with Genie](../../L100-foundations/lab-03-genie/) to use this space as a tool in an agent. Set Lab 3's `genie_space_id` widget to the value printed here.

## GenieRoomModel fields exercised

| YAML key | Object model | What it configures |
|---|---|---|
| `table_sources[].column_configs[]` | `GenieColumnConfig` | Per-column description, synonyms, sample_values, build_value_dictionary, excluded |
| `metric_view_sources[]` | `GenieMetricViewSource` | Metric views as Genie data sources |
| `function_sources[]` | `GenieSqlFunctionSource` | UC functions as trusted assets |
| `text_instructions[]` | `list[str]` | Free-form reasoning instructions |
| `example_sqls[]` | `GenieExampleSql` | Trusted question-SQL pairs with parameters and usage_guidance |
| `join_specs[]` | `GenieJoinSpec` | Declared joins with relationship_type and comment (commented out in YAML; the v2 API's SQL expression parser does not yet accept all join condition formats) |
| `sql_filters[]` | `GenieSqlSnippet` | Reusable filter snippets with synonyms |
| `sql_expressions[]` | `GenieSqlSnippet` | Reusable expression snippets |
| `sql_measures[]` | `GenieSqlSnippet` | Reusable measure snippets |
| `sample_questions[]` | `list[str]` | Suggested questions in the Genie UI |
| `benchmarks[]` | `GenieBenchmarkQuestion` | Offline evaluation question-SQL pairs |
| `entitlements[]` | `GenieEntitlement` | Workspace permissions (CAN_RUN, CAN_MANAGE) |
