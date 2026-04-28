# L100 -- Foundations

The first level of the DAO-AI workshop. Goal: by the end you'll have built four working agents -- each demonstrating one new DAO-AI concept on top of the last -- and you'll be comfortable with the declarative YAML approach.

**Use case:** [hardware_store](../README.md#use-cases). All four labs build a retail product assistant for ACME Hardware.

## Walk this level in order

| Step | Path | Type | What it covers |
|---|---|---|---|
| 1 | [setting-the-stage.md](setting-the-stage.md) | Lecture | What an agent is. Why DAO-AI uses YAML instead of code. |
| 2 | [anatomy-of-a-config.md](anatomy-of-a-config.md) | Lecture | The four sections every DAO-AI config has: `parameters`, `resources`, `agents`, `app`. |
| 3 | [lab-01-first-agent/](lab-01-first-agent/) | Lab | **Lab 1 -- Your First DAO-AI Agent.** A single LLM, no tools. Confirms your environment works. |
| 4 | [lab-02-uc-tools/](lab-02-uc-tools/) | Lab | **Lab 2 -- Grounding with Unity Catalog Tools.** Add UC SQL functions as tools so the agent stops guessing. |
| 5 | [lab-03-genie/](lab-03-genie/) | Lab | **Lab 3 -- NL Analytics with Genie.** Wrap a Databricks Genie Space as a tool for open-ended analytics. |
| 6 | [lab-04-mcp/](lab-04-mcp/) | Lab | **Lab 4 -- Schema-wide Tool Discovery with MCP.** Replace per-function declarations with one MCP block. |
| 7 | [debrief.md](debrief.md) | Debrief | Common gotchas, what surprised you, segue to L200. |

## Prerequisites

- Databricks workspace with Serverless v5 compute.
- A Unity Catalog catalog you can create schemas in (workshop convention: `workshop_<your_username>`).
- `databricks-claude-sonnet-4-5` foundation-model endpoint enabled.
- A Genie Space pointed at your workshop's `products` table (created manually before Lab 3).

## When to move on

Move to L200 once Lab 4 succeeds. The L200 labs assume you're comfortable with parameter overrides, `AppConfig.from_file`, and the `config.deploy_agent(...)` flow.
