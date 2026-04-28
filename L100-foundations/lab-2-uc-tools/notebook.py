# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 2 -- Grounding with Unity Catalog Tools
# MAGIC
# MAGIC **Level:** L100
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Declare a Unity Catalog `schemas:` block with parameter-substituted `catalog_name`.
# MAGIC - Provision a Delta table + two UC SQL functions from DDL files via `dataset.create()` / `uc_fn.create()`.
# MAGIC - Wire the UC functions as `type: unity_catalog` tools and bind them to the agent.
# MAGIC - Watch the agent stop guessing and start calling tools for SKU and category questions.
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC An agent that answers `"What Power Tools do you have under $100?"` by calling `find_products_by_category` and returns real catalog data.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 - Install dependencies

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.64"
# MAGIC %restart_python

# COMMAND ----------

from importlib.metadata import version

print(f"dao-ai={version('dao-ai')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Auto-derive username
# MAGIC
# MAGIC The deployed app name is parameterized with `${var.username}` so
# MAGIC multiple students can deploy to the same workspace without name
# MAGIC collisions. We auto-derive it from your Databricks short name.

# COMMAND ----------

import re

from databricks.sdk import WorkspaceClient
from langgraph.graph.state import CompiledStateGraph
from typing import Any

w: WorkspaceClient = WorkspaceClient()
short_name: str = w.current_user.me().user_name.split("@")[0].lower()
username: str = re.sub(r"[^a-z0-9]+", "-", short_name).strip("-")[:13]
print(f"Derived username: {username}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 - Configure parameters
# MAGIC
# MAGIC One `params` dict is reused across every step file so you only
# MAGIC set widgets once.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (e.g. workshop_jane_doe)")
dbutils.widgets.text("schema", "dao_ai", "Schema")
dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-4-5", "LLM endpoint")

catalog: str = dbutils.widgets.get("catalog").strip()
if not catalog:
    raise ValueError("Set the catalog widget at the top of the notebook.")

params: dict[str, str] = {
    "username": username,
    "catalog": catalog,
    "schema": dbutils.widgets.get("schema").strip(),
    "llm_endpoint": dbutils.widgets.get("llm_endpoint").strip(),
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 - Walk the steps
# MAGIC
# MAGIC Each step config self-declares the resources it needs in its own
# MAGIC `schemas:` / `datasets:` / `unity_catalog_functions:` blocks. We
# MAGIC provision **per step** (only what that step's config introduces),
# MAGIC not all upfront. `.create()` is idempotent so when step 3 reuses
# MAGIC the schema and table from step 2, those calls are no-ops.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3a. `01_product_assistant.yaml` -- ungrounded baseline
# MAGIC
# MAGIC Just an LLM with a prompt. No tools, no UC resources to provision.
# MAGIC Watch what happens when the agent has to answer a SKU-specific
# MAGIC question without any way to look up real data: it will either
# MAGIC guess or correctly admit it doesn't know -- both are fine.
# MAGIC **The point is to feel what ungrounded looks like.**
# MAGIC
# MAGIC ```yaml
# MAGIC # The whole config:
# MAGIC parameters: { llm_endpoint: ... }
# MAGIC resources:
# MAGIC   llms: { default_llm: ... }
# MAGIC agents:
# MAGIC   product_agent:
# MAGIC     model: *default_llm
# MAGIC     prompt: |
# MAGIC       You are a product assistant... (no tools)
# MAGIC ```

# COMMAND ----------

from dao_ai.config import AppConfig

config: AppConfig = AppConfig.from_file("01_product_assistant.yaml", params=params)
agent: CompiledStateGraph = config.as_graph()

response: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "Tell me about SKU-0001."}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3b. `02_product_assistant_with_sku_lookup.yaml` -- adds SKU lookup
# MAGIC
# MAGIC New blocks since step 1 (diff this against `01_product_chat`):
# MAGIC
# MAGIC ```yaml
# MAGIC schemas:
# MAGIC   workshop_schema: { catalog_name: ${var.catalog}, schema_name: ${var.schema} }
# MAGIC
# MAGIC resources:
# MAGIC   functions:
# MAGIC     find_product_by_sku: { schema: *workshop_schema, name: find_product_by_sku }
# MAGIC
# MAGIC tools:
# MAGIC   sku_lookup_tool:
# MAGIC     name: find_product_by_sku
# MAGIC     function: { type: unity_catalog, resource: *find_product_by_sku }
# MAGIC
# MAGIC agents:
# MAGIC   product_agent:
# MAGIC     tools: [*sku_lookup_tool]   # <-- agent now has one tool
# MAGIC ```
# MAGIC
# MAGIC Provision the resources this step introduces -- the schema, the
# MAGIC products table (datasets), and the `find_product_by_sku` UC
# MAGIC function -- then run the same SKU question. It now triggers a
# MAGIC real tool call. Watch the MLflow trace for the
# MAGIC `find_product_by_sku` span.

# COMMAND ----------

config: AppConfig = AppConfig.from_file("02_product_assistant_with_sku_lookup.yaml", params=params)

for schema in config.schemas.values():
    schema.create()
    print(f"Schema ready:   {schema.full_name}")

for dataset in config.datasets:
    dataset.create()
    print(f"Table loaded:   {dataset.table.full_name}")

for uc_fn in config.unity_catalog_functions:
    uc_fn.create()
    print(f"Function ready: {uc_fn.function.full_name}")

# COMMAND ----------

agent: CompiledStateGraph = config.as_graph()

response: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "Tell me about SKU-0001."}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC #### What about category questions?
# MAGIC
# MAGIC The step-2 agent has no category tool. It should respond
# MAGIC honestly that it can't answer this kind of question yet.

# COMMAND ----------

response: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "What Power Tools do you have under $100?"}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3c. `03_product_assistant_with_catalog_search.yaml` -- adds category browsing (final)
# MAGIC
# MAGIC New blocks since step 2:
# MAGIC
# MAGIC ```yaml
# MAGIC resources:
# MAGIC   functions:
# MAGIC     find_products_by_category: { schema: *workshop_schema, name: find_products_by_category }
# MAGIC
# MAGIC tools:
# MAGIC   category_lookup_tool:
# MAGIC     name: find_products_by_category
# MAGIC     function: { type: unity_catalog, resource: *find_products_by_category }
# MAGIC
# MAGIC agents:
# MAGIC   product_agent:
# MAGIC     tools: [*sku_lookup_tool, *category_lookup_tool]   # <-- both tools
# MAGIC     prompt: |
# MAGIC       ...rules teaching the model when to pick which tool...
# MAGIC ```
# MAGIC
# MAGIC Provision the new function (the schema + table + sku_lookup
# MAGIC function from step 2 are already in place, so those `.create()`
# MAGIC calls are idempotent no-ops). Now both kinds of questions get
# MAGIC grounded answers.

# COMMAND ----------

config: AppConfig = AppConfig.from_file("03_product_assistant_with_catalog_search.yaml", params=params)

for schema in config.schemas.values():
    schema.create()

for dataset in config.datasets:
    dataset.create()

for uc_fn in config.unity_catalog_functions:
    uc_fn.create()
    print(f"Function ready: {uc_fn.function.full_name}")

# COMMAND ----------

agent: CompiledStateGraph = config.as_graph()

try:
    config.display_graph()
except Exception as e:
    print(f"An exception has occurred: {e}")

# COMMAND ----------

response: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "What Power Tools do you have under $100?"}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

response: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "Tell me about SKU-0001."}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 - Deploy as a Databricks App
# MAGIC
# MAGIC The final step config (`03_product_assistant_with_catalog_search.yaml`)
# MAGIC is the deploy artifact. Generate an Asset Bundle from it and deploy.

# COMMAND ----------

from dao_ai.config import DeploymentTarget

config.deploy_agent(target=DeploymentTarget.APPS)
print(f"Deployed app: {config.app.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next
# MAGIC
# MAGIC [Lab 3: Genie](../lab-3-genie/) - give the agent a Databricks
# MAGIC Genie Space as a tool so it can answer natural-language
# MAGIC questions in SQL directly against the data.
