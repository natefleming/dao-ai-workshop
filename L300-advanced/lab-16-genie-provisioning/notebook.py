# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 16 -- Declarative Genie Space Provisioning
# MAGIC
# MAGIC **Level:** L300
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Provision tables, views, and UC SQL functions from SQL files via `DatasetModel.create()` and `UnityCatalogFunctionSqlModel.create()`.
# MAGIC - Provision a fully-configured Genie space from YAML via `GenieRoomModel.create()`, exercising every capability in the object model.
# MAGIC - Understand how `datasets:` + `unity_catalog_functions:` + `resources.genie_rooms:` chain into a single provisioning pipeline.
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC A Genie Space with two tables, two views, two UC functions, text instructions, example SQLs, SQL snippets, sample questions, benchmarks, and entitlements -- all declared in `genie_room.yaml`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 - Install dependencies

# COMMAND ----------

# MAGIC %uv pip install "dao-ai==0.2.5"
# MAGIC %restart_python

# COMMAND ----------

from importlib.metadata import version

print(f"dao-ai={version('dao-ai')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Auto-derive username
# MAGIC
# MAGIC The Genie space name is parameterized with `${var.username}` so
# MAGIC multiple students can provision to the same workspace without
# MAGIC name collisions.

# COMMAND ----------

import re

from databricks.sdk import WorkspaceClient

w: WorkspaceClient = WorkspaceClient()
short_name: str = w.current_user.me().user_name.split("@")[0].lower()
username: str = re.sub(r"[^a-z0-9]+", "-", short_name).strip("-")[:13]
print(f"Derived username: {username}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 - Configure parameters
# MAGIC
# MAGIC `genie_room.yaml` declares parameters in a top-level `parameters:`
# MAGIC block. We override them at load time via the `params={...}`
# MAGIC kwarg of `AppConfig.from_file`.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (e.g. workshop_jane_doe)")
dbutils.widgets.text("schema", "dao_ai", "Schema")
dbutils.widgets.text("warehouse_id", "", "SQL Warehouse ID")
dbutils.widgets.text("genie_parent_path", "", "Genie parent path (e.g. /Users/you@databricks.com/genie)")

catalog: str = dbutils.widgets.get("catalog").strip()
if not catalog:
    raise ValueError("Set the catalog widget at the top of the notebook.")

warehouse_id: str = dbutils.widgets.get("warehouse_id").strip()
if not warehouse_id:
    raise ValueError("Set the warehouse_id widget at the top of the notebook.")

genie_parent_path: str = dbutils.widgets.get("genie_parent_path").strip()
if not genie_parent_path:
    raise ValueError("Set the genie_parent_path widget at the top of the notebook.")

params: dict[str, str] = {
    "username": username,
    "catalog": catalog,
    "schema": dbutils.widgets.get("schema").strip(),
    "warehouse_id": warehouse_id,
    "genie_parent_path": genie_parent_path,
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 - Load the config
# MAGIC
# MAGIC `genie_room.yaml` is a barebones config with no `agents:` or
# MAGIC `app:` block. It declares only what's needed to provision the
# MAGIC Genie space and its dependencies:
# MAGIC
# MAGIC - `schemas:` -- the Unity Catalog schema
# MAGIC - `resources:` -- warehouses, tables, functions, and a `genie_rooms:` entry
# MAGIC - `datasets:` -- DDL + seed data for tables, a view, and a materialized view
# MAGIC - `unity_catalog_functions:` -- SQL function DDL files

# COMMAND ----------

from dao_ai.config import AppConfig

config: AppConfig = AppConfig.from_file("genie_room.yaml", params=params, initialize=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 - Provision schemas

# COMMAND ----------

for schema in config.schemas.values():
    schema.create()
    print(f"Schema ready: {schema.full_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 - Provision datasets
# MAGIC
# MAGIC Each `DatasetModel` entry in `datasets:` runs the SQL file referenced
# MAGIC by its `ddl:` field. This creates the products table, orders table,
# MAGIC the `active_products_v` view, and the `daily_sales_mv` aggregation view.

# COMMAND ----------

for dataset in config.datasets:
    dataset.create()
    print(f"Dataset ready: {dataset.table.full_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 - Provision UC SQL functions
# MAGIC
# MAGIC Each `UnityCatalogFunctionSqlModel` entry runs the DDL file, then
# MAGIC optionally invokes the function with `test.parameters` to verify it works.

# COMMAND ----------

for uc_fn in config.unity_catalog_functions:
    uc_fn.create()
    print(f"Function ready: {uc_fn.function.full_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 - Provision the Genie space
# MAGIC
# MAGIC `GenieRoomModel.create()` calls the Databricks Genie API to create
# MAGIC (or update) the space. The full configuration -- table sources with
# MAGIC column configs, metric view sources, function sources, text
# MAGIC instructions, example SQLs, join specs, SQL snippets, sample
# MAGIC questions, benchmarks, and entitlements -- is serialized from the
# MAGIC YAML into the space's `serialized_space` payload.
# MAGIC
# MAGIC After creation, `genie_room.space_id` is populated with the new
# MAGIC space's ID.

# COMMAND ----------

for genie_room in config.resources.genie_rooms.values():
    genie_room.create()
    print(f"Genie space ready: name={genie_room.name}  space_id={genie_room.space_id}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 8 - Populate a GenieRoomModel from an existing space
# MAGIC
# MAGIC `GenieRoomModel.from_space()` is the inverse of `create()`. Given a
# MAGIC `space_id`, it fetches the live space and hydrates every structured
# MAGIC field -- table sources with column configs, instructions, join specs,
# MAGIC SQL snippets, benchmarks, and more -- into a new `GenieRoomModel`
# MAGIC instance. This is useful for:
# MAGIC
# MAGIC - **Exporting** a space that was configured in the UI back to YAML.
# MAGIC - **Diffing** a YAML-defined space against the live version.
# MAGIC - **Cloning** a space: `from_space()` → modify fields → `create()`.

# COMMAND ----------

from dao_ai.config import GenieRoomModel

space_id: str = list(config.resources.genie_rooms.values())[0].space_id

room: GenieRoomModel = GenieRoomModel.from_space(space_id)

print(f"name:               {room.name}")
print(f"description:        {room.description}")
print(f"space_id:           {room.space_id}")
print(f"table_sources:      {len(room.table_sources or [])}")
print(f"metric_view_sources:{len(room.metric_view_sources or [])}")
print(f"function_sources:   {len(room.function_sources or [])}")
print(f"text_instructions:  {len(room.text_instructions or [])}")
print(f"example_sqls:       {len(room.example_sqls or [])}")
print(f"join_specs:         {len(room.join_specs or [])}")
print(f"sql_filters:        {len(room.sql_filters or [])}")
print(f"sql_expressions:    {len(room.sql_expressions or [])}")
print(f"sql_measures:       {len(room.sql_measures or [])}")
print(f"sample_questions:   {len(room.sample_questions or [])}")
print(f"benchmarks:         {len(room.benchmarks or [])}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Inspect the hydrated fields
# MAGIC
# MAGIC Each structured field was populated from the live `serialized_space`
# MAGIC JSON. You can inspect individual fields, modify them, and call
# MAGIC `room.create()` to push changes back.

# COMMAND ----------

if room.table_sources:
    for ts in room.table_sources:
        cols: int = len(ts.column_configs) if ts.column_configs else 0
        print(f"  table={ts.table.name}  columns_configured={cols}  desc={ts.description}")

if room.example_sqls:
    for ex in room.example_sqls:
        print(f"  question={ex.question!r}  params={len(ex.parameters or [])}")

if room.join_specs:
    for js in room.join_specs:
        print(f"  join: {js.left.name} -> {js.right.name}  type={js.relationship_type}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Done
# MAGIC
# MAGIC The Genie space is now live. Open it in the Databricks UI to verify
# MAGIC the data sources, instructions, and sample questions. You can pass
# MAGIC the `space_id` printed above to [Lab 3](../../L100-foundations/lab-03-genie/)
# MAGIC to use this space as a tool in an agent.
# MAGIC
# MAGIC `GenieRoomModel.from_space(space_id)` can reconstruct a model from
# MAGIC any existing space -- even ones created in the UI -- making it easy
# MAGIC to export, diff, or clone spaces programmatically.
