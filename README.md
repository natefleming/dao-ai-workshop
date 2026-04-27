# dao-ai Workshop

Self-paced, hands-on workshop for building declarative AI agents on Databricks with the [dao-ai](https://github.com/natefleming/dao-ai) framework. Designed for solution architects, data engineers, and analysts who want to go from zero to a deployed, governed agent. By the end you'll have built, tested, and deployed a multi-agent system that combines tool use, NL-to-SQL, vector search, memory, guardrails, and orchestration -- all defined in YAML and running as a Databricks App.

## Workshop structure

The workshop is organized as **L100 → L200 → L300**, mirroring the level system used in the broader Databricks training catalog. Each level contains lectures (concept framing) and labs (hands-on notebooks).

| Section | Path | Use case | Labs |
|---|---|---|---|
| **L100 Foundations** | [`l100-foundations/`](l100-foundations/) | hardware_store (consumer retail) | 4 labs |
| **L200 Building Real Agents** | [`l200-real-agents/`](l200-real-agents/) | saas_helpdesk (support ops) | 5 labs |
| **L300 Advanced** | [`l300-advanced/`](l300-advanced/) | hardware_store++ (extended) | 2 labs |

## Lab index

### L100 Foundations -- `hardware_store`

| Lab | Title | dao-ai concept | Path |
|---|---|---|---|
| **Lab 1** | Your First dao-ai Agent | Declarative single-agent LLM | [`l100-foundations/lab-1-first-agent/`](l100-foundations/lab-1-first-agent/) |
| **Lab 2** | Grounding with Unity Catalog Tools | UC SQL function tools | [`l100-foundations/lab-2-uc-tools/`](l100-foundations/lab-2-uc-tools/) |
| **Lab 3** | NL Analytics with Genie | Genie Space as a tool | [`l100-foundations/lab-3-genie/`](l100-foundations/lab-3-genie/) |
| **Lab 4** | Schema-wide Tool Discovery with MCP | Managed MCP servers | [`l100-foundations/lab-4-mcp/`](l100-foundations/lab-4-mcp/) |

L100 also ships two **lectures** before the labs: [Setting the Stage](l100-foundations/setting-the-stage.md) and [Anatomy of a dao-ai Config](l100-foundations/anatomy-of-a-config.md). Read these first.

### L200 Building Real Agents -- `saas_helpdesk`

| Lab | Title | dao-ai concept | Path |
|---|---|---|---|
| **Lab 5** | External Integrations via REST | REST factory tools | [`l200-real-agents/lab-5-rest/`](l200-real-agents/lab-5-rest/) |
| **Lab 6** | Knowledge-base Retrieval with Vector Search | Vector store + cross-encoder reranker | [`l200-real-agents/lab-6-vector-search/`](l200-real-agents/lab-6-vector-search/) |
| **Lab 7** | Persistent Memory | Lakebase checkpointer + store + extraction | [`l200-real-agents/lab-7-memory/`](l200-real-agents/lab-7-memory/) |
| **Lab 8** | Production Prompts and Guardrails | Prompt Registry + judge guardrail | [`l200-real-agents/lab-8-prompts-guardrails/`](l200-real-agents/lab-8-prompts-guardrails/) |
| **Lab 9** | Multi-agent Orchestration | Supervisor + swarm | [`l200-real-agents/lab-9-orchestration/`](l200-real-agents/lab-9-orchestration/) |

L200 starts with the [Building Real Agents](l200-real-agents/building-real-agents.md) lecture.

### L300 Advanced

| Lab | Title | dao-ai concept | Path |
|---|---|---|---|
| **Lab 10** | Instructed Retrieval | Query decomposition + cross-encoder + LLM-based instruction rerank | [`l300-advanced/lab-10-instructed-retrieval/`](l300-advanced/lab-10-instructed-retrieval/) |
| **Lab 11** | Genie Context-Aware Caching | L1 LRU exact-match + L2 similarity cache over a Genie tool | [`l300-advanced/lab-11-genie-caching/`](l300-advanced/lab-11-genie-caching/) |

See the [L300 README](l300-advanced/README.md) for production-deployment guidance.

## Why two use cases?

L100 builds a hardware-store retail assistant. L200 switches to a SaaS support coordinator. **Same dao-ai concepts; different domain framing.** The switch keeps each lab's config tightly scoped to its new feature instead of accumulating every prior chapter's setup. See the level READMEs for more.

## Per-student deployment

Every lab's `app.name` is parameterized with `${var.username}`. The notebook auto-derives a sanitized short-name from your Databricks identity and injects it into `params={...}`, so multiple students can deploy to the same workspace without app-name collisions.

Resulting deployed names are short and theme-specific:

| Lab | Deployed app name |
|---|---|
| Lab 1 | `greeter-hw-jane-doe` |
| Lab 2 | `products-hw-jane-doe` |
| Lab 3 | `product-genie-jane-doe` |
| Lab 4 | `products-mcp-jane-doe` |
| Lab 5 | `status-check-jane-doe` |
| Lab 6 | `kb-search-jane-doe` |
| Lab 7 | `support-history-jane-doe` |
| Lab 8 | `safe-support-jane-doe` |
| Lab 9 | `tier-routing-jane-doe` |
| Lab 10 | `instructed-search-jane-doe` |
| Lab 11 | `cached-analyst-jane-doe` |

All names fit within the 30-character Databricks Apps limit.

## Common deploy flow

Every lab deploys with one Python call:

```python
from dao_ai.config import DeploymentTarget
config.deploy_agent(target=DeploymentTarget.APPS)
print(f"Deployed app: {config.app.name}")
```

`deploy_agent` generates the Asset Bundle from the dao-ai config, deploys it, and runs the app. No `databricks bundle` CLI invocations from the notebook.

## Setup

| Requirement | Detail |
|---|---|
| Python | 3.11+ |
| dao-ai | `pip install "dao-ai>=0.1.58"` (the labs install this in the notebook) |
| Databricks CLI | v0.230+ with a configured profile |
| Compute | Databricks Serverless v5 |
| Foundation models | `databricks-claude-sonnet-4-5` (always); `databricks-gte-large-en` (Lab 6 + Lab 10 + Lab 11); `databricks-claude-haiku-4-5` and `databricks-meta-llama-3-1-8b-instruct` (Lab 10 + Lab 7) |
| Genie Space | One pointed at `products` (Lab 3 + Lab 11) |
| Vector Search endpoint | Used by Lab 6 + Lab 10 |
| SQL warehouse | Used by Lab 11 (Genie cache replay) |
| Lakebase access | Used by Lab 7 (in-memory fallback exists) |

## Per-student catalog isolation

Workshop convention: each student works in `workshop_<your-sanitized-username>.dao_ai`. The lab notebooks prompt for the catalog via a widget and pass it into `params={...}`. Instructors should pre-create catalogs or grant `CREATE CATALOG` to participants.

## Sync to your workspace

```bash
databricks sync . /Users/<you>@databricks.com/dao-ai-workshop \
  --profile <profile> --full
```

## Self-paced vs instructor-led

- **Self-paced**: read the level README, read the lectures, then run each lab's notebook in order. Each lab is self-contained.
- **Instructor-led**: a facilitator can use the lectures as live walk-throughs and the lab notebooks as in-person exercises. Each lab's `Goals` and `Deliverable` give attendees a clear success criterion.

## How to use

```
dao-ai-workshop/
├── README.md                 (this file)
├── l100-foundations/         L100 -- hardware_store labs
│   ├── README.md             (level overview)
│   ├── setting-the-stage.md  (lecture)
│   ├── anatomy-of-a-config.md (lecture)
│   ├── lab-1-first-agent/    (Lab 1)
│   ├── lab-2-uc-tools/       (Lab 2)
│   ├── lab-3-genie/          (Lab 3)
│   ├── lab-4-mcp/            (Lab 4)
│   └── debrief.md            (debrief)
├── l200-real-agents/         L200 -- saas_helpdesk labs
│   ├── README.md
│   ├── building-real-agents.md (lecture)
│   ├── lab-5-rest/           (Lab 5)
│   ├── lab-6-vector-search/  (Lab 6)
│   ├── lab-7-memory/         (Lab 7)
│   ├── lab-8-prompts-guardrails/ (Lab 8)
│   ├── lab-9-orchestration/  (Lab 9)
│   └── debrief.md            (debrief)
├── l300-advanced/            L300 -- advanced patterns
│   ├── README.md
│   ├── lab-10-instructed-retrieval/ (Lab 10)
│   └── lab-11-genie-caching/        (Lab 11)
├── 98-programmatic/          (sidebar: build the same agent in pure Python)
└── setup/                    (workshop setup scripts)
```

## Reference

- dao-ai framework: <https://github.com/natefleming/dao-ai>
- Canonical examples: `dao-ai/config/examples/15_complete_applications/`
