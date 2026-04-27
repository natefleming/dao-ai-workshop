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

# MAGIC %pip install "dao-ai>=0.1.61"
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
# MAGIC ## Step 3 - Provision shared resources
# MAGIC
# MAGIC Use the **final** config to create the schema, seed the products
# MAGIC table, and register both UC functions up front. `.create()` is
# MAGIC idempotent, so running this once is enough for the whole
# MAGIC notebook -- every step file will find the resources it needs
# MAGIC already in place.

# COMMAND ----------

from dao_ai.config import AppConfig

final_config: AppConfig = AppConfig.from_file("03_product_assistant_with_catalog_search.yaml", params=params)

for schema in final_config.schemas.values():
    schema.create()
    print(f"Schema ready:   {schema.full_name}")

for dataset in final_config.datasets:
    dataset.create()
    print(f"Table loaded:   {dataset.table.full_name}")

for uc_fn in final_config.unity_catalog_functions:
    uc_fn.create()
    print(f"Function ready: {uc_fn.function.full_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 - Walk the steps

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4a. `01_product_assistant.yaml` -- ungrounded baseline
# MAGIC
# MAGIC Just an LLM with a prompt. No tools. Watch what happens when
# MAGIC the agent has to answer a SKU-specific question without any way
# MAGIC to look up real data: it will either guess or correctly admit
# MAGIC it doesn't know -- both are fine. **The point is to feel what
# MAGIC ungrounded looks like.**
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

config_step1: AppConfig = AppConfig.from_file("01_product_assistant.yaml", params=params)
agent_step1: CompiledStateGraph = config_step1.as_graph()

response: dict[str, Any] = await agent_step1.ainvoke(
    {"messages": [{"role": "user", "content": "Tell me about SKU-0001."}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4b. `02_product_assistant_with_sku_lookup.yaml` -- adds SKU lookup
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
# MAGIC The same SKU question now triggers a real tool call. Watch the
# MAGIC MLflow trace for the `find_product_by_sku` span.

# COMMAND ----------

config_step2: AppConfig = AppConfig.from_file("02_product_assistant_with_sku_lookup.yaml", params=params)
agent_step2: CompiledStateGraph = config_step2.as_graph()

response: dict[str, Any] = await agent_step2.ainvoke(
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

response: dict[str, Any] = await agent_step2.ainvoke(
    {"messages": [{"role": "user", "content": "What Power Tools do you have under $100?"}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4c. `03_product_assistant_with_catalog_search.yaml` -- adds category browsing (final)
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
# MAGIC Now both kinds of questions get grounded answers.

# COMMAND ----------

config: AppConfig = AppConfig.from_file("03_product_assistant_with_catalog_search.yaml", params=params)
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
# MAGIC ## Step 5 - Deploy as a Databricks App
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
# MAGIC [Chapter 3: Genie](../lab-3-genie/) - give the agent a Databricks
# MAGIC Genie Space as a tool so it can answer natural-language
# MAGIC questions in SQL directly against the data.
