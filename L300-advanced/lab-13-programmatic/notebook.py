# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 13 -- Programmatic Construction
# MAGIC
# MAGIC **Level:** L300 (advanced)
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Re-implement **Lab 4's MCP agent** -- the final L100 lab, with workshop-schema parameters, two UC functions provisioned via DDL, two MCP tools, products dataset, and full Apps deployment -- using only the DAO-AI Python object model. No YAML.
# MAGIC - Show that a Python-built `AppConfig` is structurally identical to a YAML-loaded one -- same provisioning calls, same `as_graph()` compile, same `deploy_agent()` shape.
# MAGIC - Demonstrate the workflow you'd reach for when generating agents dynamically (one per tenant, one per dataset) or embedding DAO-AI inside a larger Python application.
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC A `hardware-store-<your-username>` agent that does everything Lab 4's MCP agent does -- discovers UC functions in the workshop schema, runs ad-hoc SQL via the managed SQL MCP, and answers product questions over the provisioned `products` table -- built end-to-end from Python. Reuses the L100 hardware_store app slot; redeploying replaces the previous lab's agent with this one.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 -- Install dependencies

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.70"
# MAGIC %restart_python

# COMMAND ----------

from importlib.metadata import version

print(f"dao-ai={version('dao-ai')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 -- Configure parameters
# MAGIC
# MAGIC Same per-student username pattern as the YAML labs, just resolved in Python instead of via `${var.username}`.

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
schema_name: str = dbutils.widgets.get("schema").strip()
llm_endpoint: str = dbutils.widgets.get("llm_endpoint").strip()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 -- Build the config in Python
# MAGIC
# MAGIC Each block below is the Python equivalent of the matching YAML block in `L100-foundations/lab-04-mcp/mcp_assistant.yaml`. Compare side by side to see how `${var.NAME}` substitution maps to Python f-strings, anchors map to plain Python references, and `&workshop_schema` / `*workshop_schema` becomes a single shared `SchemaModel` instance.

# COMMAND ----------

from dao_ai.config import (
    AgentModel,
    AppConfig,
    AppModel,
    ChatPayload,
    DatasetModel,
    DeploymentTarget,
    FunctionModel,
    LLMModel,
    McpFunctionModel,
    Message,
    ResourcesModel,
    SchemaModel,
    TableModel,
    ToolModel,
    UnityCatalogFunctionSqlModel,
)

# 3a. Workshop schema (YAML: schemas: workshop_schema:).
workshop_schema: SchemaModel = SchemaModel(
    catalog_name=catalog,
    schema_name=schema_name,
)

# 3b. LLM resource (YAML: resources.llms.default_llm:).
default_llm: LLMModel = LLMModel(
    name=llm_endpoint,
    temperature=0.1,
    max_tokens=4096,
)

# 3c. UC function declarations (YAML: resources.functions:). MCP discovery
# happens at agent-build time, so the functions need to exist in the schema
# before `as_graph()` runs -- same constraint as the YAML version.
find_product_by_sku: FunctionModel = FunctionModel(
    schema=workshop_schema,
    name="find_product_by_sku",
)
find_products_by_category: FunctionModel = FunctionModel(
    schema=workshop_schema,
    name="find_products_by_category",
)

# 3d. MCP tools (YAML: tools.functions_mcp + tools.sql_mcp).
functions_mcp: ToolModel = ToolModel(
    name="functions_mcp",
    function=McpFunctionModel(functions=workshop_schema),
)
sql_mcp: ToolModel = ToolModel(
    name="sql_mcp",
    function=McpFunctionModel(sql=True),
)

# 3e. The MCP agent (YAML: agents.mcp_agent).
mcp_agent: AgentModel = AgentModel(
    name="mcp_agent",
    description="Agent backed by managed MCP servers for UC functions and SQL.",
    model=default_llm,
    tools=[functions_mcp, sql_mcp],
    prompt=(
        "You have access to Unity Catalog functions and a SQL execution "
        "tool through MCP. Prefer UC functions when available (they have "
        "typed parameters and audit trails). Use SQL for ad-hoc queries "
        "that UC functions don't cover.\n\n"
        "When you call a SQL tool, qualify every table with the full "
        "three-part name: catalog.schema.table_name."
    ),
)

# 3f. Self-contained provisioning: products table + UC functions
# (YAML: datasets: + unity_catalog_functions:).
datasets: list[DatasetModel] = [
    DatasetModel(
        table=TableModel(schema=workshop_schema, name="products"),
        ddl="./data/products.sql",
        format="sql",
    ),
]

unity_catalog_functions: list[UnityCatalogFunctionSqlModel] = [
    UnityCatalogFunctionSqlModel(
        function=find_product_by_sku,
        ddl="./functions/find_product_by_sku.sql",
        test={"parameters": {"sku": ["SKU-0001"]}},
    ),
    UnityCatalogFunctionSqlModel(
        function=find_products_by_category,
        ddl="./functions/find_products_by_category.sql",
        test={"parameters": {"category": "Power Tools"}},
    ),
]

# 3g. The deployable app (YAML: app:).
app: AppModel = AppModel(
    name=f"hardware-store-{username}",
    description="Lab 13 (hardware_store): Lab 4's MCP agent built in pure Python.",
    log_level="INFO",
    deployment_target=DeploymentTarget.APPS,
    agents=[mcp_agent],
    # No orchestration: needed -- single-agent apps don't require it.
    input_example=ChatPayload(
        input=[Message(role="user", content="List 3 power tools from our catalog.")],
    ),
)

# 3h. Stitch it together.
config: AppConfig = AppConfig(
    schemas={"workshop_schema": workshop_schema},
    resources=ResourcesModel(
        llms={"default_llm": default_llm},
        functions={
            "find_product_by_sku": find_product_by_sku,
            "find_products_by_category": find_products_by_category,
        },
    ),
    tools={"functions_mcp": functions_mcp, "sql_mcp": sql_mcp},
    agents={"mcp_agent": mcp_agent},
    app=app,
    datasets=datasets,
    unity_catalog_functions=unity_catalog_functions,
)

print(f"Compiled app name: {config.app.name}")
print(f"Schemas: {list(config.schemas.keys())}")
print(f"Functions: {list(config.resources.functions.keys())}")
print(f"Tools: {list(config.tools.keys())}")
print(f"Agents: {list(config.agents.keys())}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- Provision schema, products table, and UC functions
# MAGIC
# MAGIC The MCP `functions:` tool discovers every UC function in the schema at agent-build time, so the functions need to exist **before** `as_graph()` runs. This is exactly the same dance as Lab 4's notebook -- the only difference is `config` came from Python, not YAML.

# COMMAND ----------

for s in config.schemas.values():
    s.create()
    print(f"Schema ready:    {s.full_name}")

for dataset in config.datasets:
    dataset.create()
    print(f"Dataset applied: {dataset.table.full_name}")

for uc_fn in config.unity_catalog_functions:
    uc_fn.create()
    print(f"Function ready:  {uc_fn.function.full_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 -- Compile and test locally

# COMMAND ----------

agent: CompiledStateGraph = config.as_graph()
try:
    config.display_graph()
except Exception as e:
    print(f"display_graph: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Question that should hit a UC function

# COMMAND ----------

# MAGIC %md
# MAGIC ### Enable MLflow autolog
# MAGIC
# MAGIC `mlflow.langchain.autolog()` registers tracers on every LangChain
# MAGIC call so the agent's tool calls, LLM completions, and graph
# MAGIC transitions land in the active MLflow experiment as traces.
# MAGIC Open the Experiment from the right-hand panel after running an
# MAGIC inference cell below to inspect what the agent did.

# COMMAND ----------

import mlflow

mlflow.langchain.autolog()

# COMMAND ----------

response: dict[str, Any] = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "List 3 power tools from our catalog."}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Question that requires ad-hoc SQL (no pre-built function)

# COMMAND ----------

response = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "What's the average price across all products?"}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Stream the same agent in ResponsesAgent shape
# MAGIC
# MAGIC The Python-built `AppConfig` exposes the same alternate paths
# MAGIC as a YAML-loaded one. `as_responses_agent()` returns the
# MAGIC OpenAI-style ResponsesAgent the deployed app exposes;
# MAGIC `process_messages_stream(...)` from `dao_ai.models` runs it in
# MAGIC streaming mode so partial deltas surface as the agent thinks.

# COMMAND ----------

from dao_ai.models import process_messages_stream
from mlflow.pyfunc import ResponsesAgent
from mlflow.types.responses import ResponsesAgentStreamEvent

responses_agent: ResponsesAgent = config.as_responses_agent()
event: ResponsesAgentStreamEvent
for event in process_messages_stream(
    responses_agent,
    [{"role": "user", "content": "Recommend two power tools under $100 and explain why."}],
):
    delta: str | None = getattr(event, "delta", None)
    if delta:
        print(delta, end="", flush=True)
print()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 -- Deploy as a Databricks App
# MAGIC
# MAGIC `deploy_agent` doesn't care whether the `AppConfig` came from YAML or Python -- it serializes the in-memory object either way.

# COMMAND ----------

config.deploy_agent(target=DeploymentTarget.APPS)
print(f"Deployed app: {config.app.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## When to use this vs YAML
# MAGIC
# MAGIC - **YAML wins** when the config is mostly static, you want config-as-code review, or non-developers will edit it.
# MAGIC - **Python wins** when you generate configs dynamically: one agent per tenant from a database query, one config per dataset in a sweep, programmatic A/B tests, or embedding DAO-AI inside a larger Python application.
# MAGIC - **Mixing is fine**: load a YAML with `AppConfig.from_file(...)`, then mutate fields on the returned object before `as_graph()` / `deploy_agent()`.
# MAGIC
# MAGIC The two paths produce structurally identical `AppConfig` objects. Pick whichever fits your workflow.
