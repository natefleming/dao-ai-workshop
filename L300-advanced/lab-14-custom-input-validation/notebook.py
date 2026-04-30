# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 14 -- Custom-Input Validation
# MAGIC
# MAGIC **Level:** L300 (advanced)
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Wire `dao_ai.middleware.create_custom_field_validation_middleware` into an agent so missing per-call context returns a markdown error before the model runs.
# MAGIC - See the difference between **required** and **optional** fields (`required: false`).
# MAGIC - Use validated context fields (`{store_num}`, `{customer_tier}`, `{region}`) directly inside the agent's system prompt and a UC tool's arguments.
# MAGIC - Watch the workflow short-circuit on a bad call vs run a real tool call on a good one.
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC A `hardware-store-<your-username>` agent that refuses requests missing `store_num` / `customer_tier`, and -- when context is supplied -- recommends products whose price fits the customer's tier (bronze/silver/gold/platinum).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC **Use case:** `hardware_store++` -- the Lab 2 `product_assistant` extended with per-store / per-tier customer context.
# MAGIC
# MAGIC **DAO-AI concept:** Middleware-based input validation. Declarative `fields:` schema produces copy-paste-ready error messages without writing any Python.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 -- Install dependencies

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.67"
# MAGIC %restart_python

# COMMAND ----------

from importlib.metadata import version

print(f"dao-ai={version('dao-ai')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 -- Configure parameters
# MAGIC
# MAGIC Same per-student username pattern as the rest of L100/L300 labs. The `catalog` widget controls which Unity Catalog catalog the workshop assets land in (the lab's products table + tier-aware UC function).

# COMMAND ----------

import re
from typing import Any

from databricks.sdk import WorkspaceClient
from langgraph.graph.state import CompiledStateGraph

w: WorkspaceClient = WorkspaceClient()
short_name: str = w.current_user.me().user_name.split("@")[0].lower()
username: str = re.sub(r"[^a-z0-9]+", "-", short_name).strip("-")[:13]
print(f"Derived username: {username}")

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
# MAGIC ## Step 3 -- Provision the products table + tier-aware UC function
# MAGIC
# MAGIC Each lab self-provisions its own dependencies via dao-ai's `.create()` SDK. Reuses Lab 2's products DDL and adds a new tier-aware function that takes `customer_tier` as an argument and applies a price ceiling.

# COMMAND ----------

from dao_ai.config import AppConfig

config: AppConfig = AppConfig.from_file("validated_advisor.yaml", params=params)

for s in config.schemas.values():
    s.create()
    print(f"Schema ready:    {s.full_name}")

for dataset in config.datasets:
    dataset.create()
    print(f"Table loaded:    {dataset.table.full_name}")

for uc_fn in config.unity_catalog_functions:
    uc_fn.create()
    print(f"Function ready:  {uc_fn.function.full_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- The validation block
# MAGIC
# MAGIC ```yaml
# MAGIC middleware:
# MAGIC   store_validation:
# MAGIC     name: dao_ai.middleware.create_custom_field_validation_middleware
# MAGIC     args:
# MAGIC       fields:
# MAGIC         - name: store_num
# MAGIC           description: "Your store number for inventory lookups (e.g. DEN-FLAG)"
# MAGIC           example_value: "DEN-FLAG"
# MAGIC         - name: customer_tier
# MAGIC           description: "Loyalty tier (bronze | silver | gold | platinum)"
# MAGIC           example_value: "gold"
# MAGIC         - name: region
# MAGIC           description: "Region for inventory routing"
# MAGIC           required: false
# MAGIC           example_value: "northeast"
# MAGIC ```
# MAGIC
# MAGIC The validator runs **before** the agent. Two fields are required (`store_num`, `customer_tier`); `region` is optional. dao-ai's `CustomFieldValidationMiddleware` reads the request's `custom_inputs.configurable` dict, checks for each required field, and -- on miss -- returns a markdown response with a copy-paste-ready JSON config.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 -- Compile the agent + enable MLflow autolog
# MAGIC
# MAGIC `mlflow.langchain.autolog()` registers tracers on every LangChain call so the validation middleware's short-circuit and the agent's tool calls land in the active MLflow experiment as traces. Open the Experiment from the right-hand panel after running an inference cell to inspect what happened.

# COMMAND ----------

import mlflow

mlflow.langchain.autolog()

agent: CompiledStateGraph = config.as_graph()

print(f"Compiled app name: {config.app.name}")
try:
    config.display_graph()
except Exception as e:
    print(f"display_graph: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 -- Test locally
# MAGIC
# MAGIC Three pedagogical invocations to feel the difference between failing and passing the validation contract.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 6a. Failure case: no `custom_inputs.configurable` at all
# MAGIC
# MAGIC The agent's middleware short-circuits before the model runs. Expect a markdown response listing the missing fields and a copy-paste JSON template the caller can paste into their next request.

# COMMAND ----------

response: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "What Power Tools do you have under $200?"}]},
    config={"configurable": {}},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 6b. Success case: full required + optional context supplied
# MAGIC
# MAGIC With `store_num`, `customer_tier`, and `region` all provided, validation passes, the agent receives the context in its prompt, calls the tier-aware UC function, and recommends products whose price fits the customer's tier.

# COMMAND ----------

response = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "What Power Tools do you have for me?"}]},
    config={"configurable": {
        "store_num": "DEN-FLAG",
        "customer_tier": "gold",
        "region": "northeast",
    }},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 6c. Required-only case: omit the optional `region`
# MAGIC
# MAGIC `region` is `required: false`, so leaving it out is fine -- the agent runs but the prompt-substituted `{region}` resolves to an empty string. Watch the recommendation come back successfully.

# COMMAND ----------

response = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "Anything in the Paint category that fits my tier?"}]},
    config={"configurable": {
        "store_num": "DEN-FLAG",
        "customer_tier": "silver",
    }},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 6d. Bonus: required field present but with an off-tier value
# MAGIC
# MAGIC Validation only checks **presence** -- it doesn't enforce enum membership. `customer_tier=diamond` passes the validator (the field is there), but the UC function won't match any tier-fit rows, so the agent should note the unknown tier and suggest a known one.

# COMMAND ----------

response = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "Show me Power Tools."}]},
    config={"configurable": {
        "store_num": "DEN-FLAG",
        "customer_tier": "diamond",
    }},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 -- Deploy as a Databricks App
# MAGIC
# MAGIC Same `app.name: hardware-store-<your-username>` slot as Labs 1, 2, 3, 4, 11, 12, 13. Redeploying replaces whichever lab's agent was last in the slot with this validated advisor.

# COMMAND ----------

from dao_ai.config import DeploymentTarget

config.deploy_agent(target=DeploymentTarget.APPS)
print(f"Deployed app: {config.app.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next
# MAGIC
# MAGIC [Lab 15 -- Long-Running / Background Agents](../lab-15-long-running/) -- Responses-API kickoff/poll/cancel for slow tasks, with state persisted in Lakebase.
