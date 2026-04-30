# DAO-AI Workshop

Self-paced, hands-on workshop for building declarative AI agents on Databricks with the [DAO-AI](https://github.com/natefleming/dao-ai) framework. Designed for solution architects, data engineers, and analysts who want to go from zero to a deployed, governed agent. By the end you'll have built, tested, and deployed a multi-agent system that combines tool use, NL-to-SQL, vector search, memory + chat-history summarization, prompts + guardrails, and orchestration -- all defined in YAML and running as a Databricks App.

## Companion projects

| Repo | What it is | When to reach for it |
|---|---|---|
| **[`dao-ai`](https://github.com/natefleming/dao-ai)** | The DAO-AI framework itself: schema, runtime, deploy primitives. Every lab in this workshop installs it via `pip install "dao-ai>=0.1.64"`. | Read the framework source, file issues, contribute features, or check the canonical examples under [`config/examples/`](https://github.com/natefleming/dao-ai/tree/main/config/examples). |
| **[`dao-ai-builder`](https://github.com/natefleming/dao-ai-builder)** | Visual builder for DAO-AI configs -- forms and dropdowns instead of hand-written YAML. Exports a ready-to-deploy `dao_ai.yaml`. | Once you've finished L100 and want a faster authoring loop for new agents, or to hand the config surface to non-developer collaborators. |

If you're wondering "where do these agents actually live in code?" the answer is `dao-ai`. If you're wondering "is there a UI for this?" the answer is `dao-ai-builder`.

## Workshop structure

The workshop is organized as **L100 → L200 → L300**, mirroring the level system used in the broader Databricks training catalog. Each level contains lectures (concept framing) and labs (hands-on notebooks).

| Section | Path | Use case | Labs |
|---|---|---|---|
| **L100 Foundations** | [`L100-foundations/`](L100-foundations/) | hardware_store (consumer retail) | 4 labs |
| **L200 Building Real Agents** | [`L200-real-agents/`](L200-real-agents/) | saas_helpdesk (support ops) | 6 labs |
| **L300 Advanced** | [`L300-advanced/`](L300-advanced/) | hardware_store++ (extended) | 5 labs |

## Lab index

### L100 Foundations -- `hardware_store`

| Lab | Title | DAO-AI concept | Path |
|---|---|---|---|
| **Lab 1** | Your First DAO-AI Agent | Declarative single-agent LLM | [`L100-foundations/lab-01-first-agent/`](L100-foundations/lab-01-first-agent/) |
| **Lab 2** | Grounding with Unity Catalog Tools | UC SQL function tools | [`L100-foundations/lab-02-uc-tools/`](L100-foundations/lab-02-uc-tools/) |
| **Lab 3** | NL Analytics with Genie | Genie Space as a tool | [`L100-foundations/lab-03-genie/`](L100-foundations/lab-03-genie/) |
| **Lab 4** | Schema-wide Tool Discovery with MCP | Managed MCP servers | [`L100-foundations/lab-04-mcp/`](L100-foundations/lab-04-mcp/) |

L100 also ships two **lectures** before the labs: [Setting the Stage](L100-foundations/setting-the-stage.md) and [Anatomy of a DAO-AI Config](L100-foundations/anatomy-of-a-config.md). Read these first.

### L200 Building Real Agents -- `saas_helpdesk`

| Lab | Title | DAO-AI concept | Path |
|---|---|---|---|
| **Lab 5** | External Integrations via REST | REST factory tools | [`L200-real-agents/lab-05-rest/`](L200-real-agents/lab-05-rest/) |
| **Lab 6** | Knowledge-base Retrieval with Vector Search | Vector store + cross-encoder reranker | [`L200-real-agents/lab-06-vector-search/`](L200-real-agents/lab-06-vector-search/) |
| **Lab 7** | Persistent Memory + Chat Summarization | Lakebase checkpointer + long-term store + extraction, plus `app.chat_history` auto-summarization | [`L200-real-agents/lab-07-memory/`](L200-real-agents/lab-07-memory/) |
| **Lab 8** | Production Prompts and Guardrails | Prompt Registry + judge guardrail | [`L200-real-agents/lab-08-prompts-guardrails/`](L200-real-agents/lab-08-prompts-guardrails/) |
| **Lab 9** | Multi-agent Orchestration | Supervisor + swarm | [`L200-real-agents/lab-09-orchestration/`](L200-real-agents/lab-09-orchestration/) |
| **Lab 10** | Human in the Loop | Tool-level approval gating with `human_in_the_loop:` (approve / edit / reject) | [`L200-real-agents/lab-10-hitl/`](L200-real-agents/lab-10-hitl/) |

L200 starts with the [Building Real Agents](L200-real-agents/building-real-agents.md) lecture.

### L300 Advanced

| Lab | Title | DAO-AI concept | Path |
|---|---|---|---|
| **Lab 11** | Instructed Retrieval | Query decomposition + cross-encoder + LLM-based instruction rerank | [`L300-advanced/lab-11-instructed-retrieval/`](L300-advanced/lab-11-instructed-retrieval/) |
| **Lab 12** | Genie Context-Aware Caching | L1 LRU exact-match + L2 similarity cache over a Genie tool | [`L300-advanced/lab-12-genie-caching/`](L300-advanced/lab-12-genie-caching/) |
| **Lab 13** | Programmatic Construction | Build the same `AppConfig` in pure Python instead of YAML | [`L300-advanced/lab-13-programmatic/`](L300-advanced/lab-13-programmatic/) |
| **Lab 14** | Custom-Input Validation | Middleware-based validation of `custom_inputs.configurable` (`store_num`, `customer_tier`, `region`) | [`L300-advanced/lab-14-custom-input-validation/`](L300-advanced/lab-14-custom-input-validation/) |
| **Lab 15** | Long-Running / Background Agents | `app.long_running:` + Lakebase-backed responses store + Responses-API kickoff/poll/cancel | [`L300-advanced/lab-15-long-running/`](L300-advanced/lab-15-long-running/) |

See the [L300 README](L300-advanced/README.md) for production-deployment guidance.

## Why two use cases?

L100 builds a hardware-store retail assistant. L200 switches to a SaaS support coordinator. **Same DAO-AI concepts; different domain framing.** The switch keeps each lab's config tightly scoped to its new feature instead of accumulating every prior chapter's setup. See the level READMEs for more.

## Per-student deployment

Every lab's `app.name` is parameterized with `${var.username}`. The notebook auto-derives a sanitized short-name from your Databricks identity and injects it into `params={...}`, so multiple students can deploy to the same workspace without app-name collisions.

**Apps are reused per use case.** Each Databricks Apps deploy redeploys the use case's existing app rather than creating a new one — only the description and underlying agent change between labs. This keeps the workspace's app count manageable across the 13 labs:

| Use case | Labs | Deployed app name |
|---|---|---|
| Hardware store (L100 + L300) | Lab 1 · 2 · 3 · 4 · 11 · 12 · 13 | `hardware-store-jane-doe` |
| SaaS helpdesk (L200) | Lab 5 · 6 · 7 · 8 · 9 · 10 | `saas-helpdesk-jane-doe` |

Each lab's `app.description` updates to reflect what that lab's redeploy adds, so you can see in the Databricks Apps UI which lab last deployed.

All names fit within the 30-character Databricks Apps limit.

## Common deploy flow

Every lab deploys with one Python call:

```python
from dao_ai.config import DeploymentTarget
config.deploy_agent(target=DeploymentTarget.APPS)
print(f"Deployed app: {config.app.name}")
```

`deploy_agent` generates the Asset Bundle from the DAO-AI config, deploys it, and runs the app. No `databricks bundle` CLI invocations from the notebook.

## Setup

| Requirement | Detail |
|---|---|
| Python | 3.11+ |
| DAO-AI | `pip install "dao-ai>=0.1.64"` (the labs install this in the notebook) |
| Databricks CLI | v0.230+ with a configured profile |
| Compute | Databricks Serverless v5 |
| Foundation models | `databricks-claude-sonnet-4-5` (always); `databricks-gte-large-en` (Lab 6 + Lab 11 + Lab 12); `databricks-claude-haiku-4-5` and `databricks-meta-llama-3-1-8b-instruct` (Lab 9 + Lab 11); `databricks-gpt-5-nano` (Lab 7 summarization); `databricks-gpt-oss-120b` (Lab 7 memory queries) |
| Genie Space | One pointed at `products` (Lab 3 + Lab 12) |
| Vector Search endpoint | Used by Lab 6 + Lab 11 |
| SQL warehouse | Used by Lab 12 (Genie cache replay) |
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
├── L100-foundations/         L100 -- hardware_store labs
│   ├── README.md             (level overview)
│   ├── setting-the-stage.md  (lecture)
│   ├── anatomy-of-a-config.md (lecture)
│   ├── lab-01-first-agent/    (Lab 1)
│   ├── lab-02-uc-tools/       (Lab 2)
│   ├── lab-03-genie/          (Lab 3)
│   ├── lab-04-mcp/            (Lab 4)
│   └── debrief.md            (debrief)
├── L200-real-agents/         L200 -- saas_helpdesk labs
│   ├── README.md
│   ├── building-real-agents.md (lecture)
│   ├── lab-05-rest/           (Lab 5)
│   ├── lab-06-vector-search/  (Lab 6)
│   ├── lab-07-memory/         (Lab 7)
│   ├── lab-08-prompts-guardrails/ (Lab 8)
│   ├── lab-09-orchestration/  (Lab 9)
│   └── debrief.md            (debrief)
├── L300-advanced/            L300 -- advanced patterns
│   ├── README.md
│   ├── lab-11-instructed-retrieval/ (Lab 11)
│   ├── lab-12-genie-caching/        (Lab 12)
│   └── lab-13-programmatic/         (Lab 13 -- build the same agent in pure Python)
└── setup/                    (workshop setup scripts)
```

## Reference

- DAO-AI framework: <https://github.com/natefleming/dao-ai>
- Canonical examples: `dao-ai/config/examples/15_complete_applications/`
