# Lab 4 -- Schema-wide Tool Discovery with MCP

**Level:** L100

## Goals

- Replace per-function tool declarations with a single `type: mcp` block referencing the schema.
- Add a serverless DBSQL MCP tool for ad-hoc queries that no UC function covers.
- Confirm the agent auto-discovers Lab 2's UC functions without re-declaring them.

## Deliverable

An `mcp_assistant` that answers both a UC-function question (`"List 3 power tools"`) and an ad-hoc SQL question (`"What's the average price?"`) without any per-function YAML.

---

**Use case:** `hardware_store` -- the agent now discovers tools by asking the schema instead of being hand-fed each one.

**DAO-AI concept:** **Managed MCP servers.** One YAML block exposes every UC function in a schema as a tool. Add a UC function tomorrow; the agent picks it up on the next load.

## What you'll learn

- The `tools.<name>.function.type: mcp` shape with `functions: <schema_anchor>` and `sql: true`.
- How managed MCP authenticates as the calling identity (no service-principal wrangling).
- The trade-off: scale (auto-discovery) vs. control (per-function declarations).

## Files

| File | Purpose |
|---|---|
| `mcp_assistant.yaml` | Two MCP tools: schema-wide UC functions + ad-hoc SQL. |
| `notebook.py` | Build, test (UC function call + ad-hoc SQL call), deploy. |

## Prerequisites

- Lab 2 run -- UC functions must exist in `<your_catalog>.dao_ai.*`.
- `databricks-claude-sonnet-4-5` foundation-model endpoint enabled.

## Run

Open `notebook.py`. Set the `catalog` widget. The notebook tests both an MCP-discovered UC function call and a serverless SQL call.

Deployed app name: `hardware-store-<your-username>`.

## Next

[Lab 5](../../L200-real-agents/lab-05-rest/) -- **switch use case** to a SaaS helpdesk and call an external HTTP API for upstream-status checks.
