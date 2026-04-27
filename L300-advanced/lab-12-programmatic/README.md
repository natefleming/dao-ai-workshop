# Lab 12 -- Programmatic Construction

**Level:** L300 (advanced)

## Goals

- Re-implement **Lab 4's MCP agent** -- the final L100 lab, with workshop-schema parameters, two UC functions provisioned via DDL, two MCP tools, products dataset, and full Apps deployment -- using only the DAO-AI Python object model. **No YAML file is involved.**
- Show that a Python-built `AppConfig` is structurally identical to a YAML-loaded one: same `schema.create()` / `dataset.create()` / `uc_fn.create()` provisioning calls, same `as_graph()` compile, same `deploy_agent()` shape.
- Demonstrate the workflow you'd reach for when generating agents dynamically (one per tenant, one per dataset) or embedding DAO-AI inside a larger Python application.

## Deliverable

A `programmatic-<your-username>` agent that does **everything Lab 4's MCP agent does** -- discovers UC functions in the workshop schema, runs ad-hoc SQL via the managed SQL MCP, and answers product questions over the provisioned `products` table -- built end-to-end from Python.

---

**Use case:** the same `hardware_store` products agent from L100 Lab 4. We pick this deliberately as the most-feature-complete L100 lab so the programmatic example exercises every common shape: parameters, schemas, resources (LLM + UC functions), tools (MCP), agents, app + orchestration + input_example, datasets, and unity_catalog_functions.

**DAO-AI concept:** the in-memory `AppConfig` object model is the same target whether you load it from YAML or build it from Python. Both round-trip cleanly through `as_graph()` and `deploy_agent()`.

## Side-by-side mapping

| Lab 4 YAML construct | Lab 12 Python equivalent |
|---|---|
| `parameters: { catalog: ..., schema: ..., llm_endpoint: ... }` | `dbutils.widgets.text(...)` + Python variables resolved before building the config |
| `schemas: workshop_schema: &workshop_schema` | `workshop_schema = SchemaModel(catalog_name=..., schema_name=...)` |
| `resources.llms.default_llm: &default_llm` | `default_llm = LLMModel(name=..., temperature=0.1, max_tokens=4096)` |
| `resources.functions.find_product_by_sku:` | `find_product_by_sku = FunctionModel(schema=workshop_schema, name="find_product_by_sku")` |
| `tools.functions_mcp: { function: { type: mcp, functions: *workshop_schema } }` | `ToolModel(name="functions_mcp", function=McpFunctionModel(functions=workshop_schema))` |
| `tools.sql_mcp: { function: { type: mcp, sql: true } }` | `ToolModel(name="sql_mcp", function=McpFunctionModel(sql=True))` |
| `agents.mcp_agent: { tools: [*functions_mcp, *sql_mcp], ... }` | `AgentModel(name="mcp_agent", tools=[functions_mcp, sql_mcp], ...)` |
| `app: { agents: [*mcp_agent], orchestration: { swarm: { default_agent: *mcp_agent } } }` | `AppModel(agents=[mcp_agent], orchestration=OrchestrationModel(swarm=SwarmModel(default_agent=mcp_agent)))` |
| `unity_catalog_functions: [{ function: *find_product_by_sku, ddl: ..., test: ... }, ...]` | `UnityCatalogFunctionSqlModel(function=find_product_by_sku, ddl=..., test={"parameters": {...}})` |
| `datasets: [{ table: ..., ddl: ..., format: sql }]` | `DatasetModel(table=TableModel(schema=workshop_schema, name="products"), ddl=..., format="sql")` |
| `${var.catalog}` substitution at load time | Python f-string / variable interpolation before constructing the model |

The right-hand column is what you write in `notebook.py`. The two surfaces are interchangeable.

## Files

| File | Purpose |
|---|---|
| `notebook.py` | The full Python build of Lab 4: provision -> compile -> test -> deploy. |
| `data/products.sql` | Same products DDL as Lab 4 (DROP IF EXISTS + CREATE + INSERT). |
| `functions/find_product_by_sku.sql` | UC SQL function DDL, same as Lab 4. |
| `functions/find_products_by_category.sql` | UC SQL function DDL, same as Lab 4. |

## Prerequisites

- Same as Lab 4: a Unity Catalog catalog you can create schemas in, the `databricks-claude-sonnet-4-5` endpoint enabled.
- This lab is **self-contained** -- it provisions its own schema, table, and functions. Lab 4 is not a prerequisite.

## Run

Open `notebook.py`. Set `catalog`. The notebook builds the `AppConfig` in Python, provisions the schema/table/functions, runs two test queries against the local agent, and deploys the result as a Databricks App.

Deployed app name: `programmatic-<your-username>`.

## When to use this vs YAML

- **YAML wins** when the config is mostly static, you want config-as-code review, or non-developers will edit it.
- **Python wins** when you generate configs dynamically: one agent per tenant from a database query, one config per dataset in a sweep, programmatic A/B tests, or embedding DAO-AI inside a larger Python application.
- **Mixing is fine**: load a YAML with `AppConfig.from_file(...)`, then mutate fields on the returned object before `as_graph()` / `deploy_agent()`.

## Back to the workshop

[Workshop README](../../README.md) | [L300 Advanced](../README.md)
