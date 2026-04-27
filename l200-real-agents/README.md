# L200 -- Building Real Agents

The second level of the dao-ai workshop. Goal: by the end you'll have built a SaaS support coordinator that integrates external services, retrieves from a knowledge base, remembers customers across sessions, has quality guardrails, and routes between specialist agents.

**Use case:** [saas_helpdesk](../README.md#use-cases). The five labs build a tier-1 support assistant for a SaaS company.

> **Why a different use case?** L100 built a hardware-store retail assistant -- great for tool-driven Q&A. L200's patterns (memory, multi-agent, accuracy guardrails) are most natural in an internal-ops context. **The dao-ai concepts are identical; only the domain framing changes**, which keeps each lab's config tightly scoped to its new feature.

## Walk this level in order

| Step | Path | Type | What it covers |
|---|---|---|---|
| 1 | [building-real-agents.md](building-real-agents.md) | Lecture | What separates a demo from production. The five patterns L200 covers. |
| 2 | [lab-5-rest/](lab-5-rest/) | Lab | **Lab 5 -- External Integrations via REST.** Wrap a public HTTP API as a tool. |
| 3 | [lab-6-vector-search/](lab-6-vector-search/) | Lab | **Lab 6 -- Knowledge-base Retrieval with Vector Search.** ANN + cross-encoder reranking. |
| 4 | [lab-7-memory/](lab-7-memory/) | Lab | **Lab 7 -- Persistent Memory.** Lakebase checkpointer + long-term store + extraction. |
| 5 | [lab-8-prompts-guardrails/](lab-8-prompts-guardrails/) | Lab | **Lab 8 -- Production Prompts and Guardrails.** Prompt Registry + judge LLM. |
| 6 | [lab-9-orchestration/](lab-9-orchestration/) | Lab | **Lab 9 -- Multi-agent Orchestration.** Tier-1 / tier-2 / escalation specialists. |
| 7 | [debrief.md](debrief.md) | Debrief | Reflection on production patterns; pointer to Wrap / L300. |

## Prerequisites

L100 completed (or you're comfortable with parameter overrides, `AppConfig.from_file`, and `config.deploy_agent(...)`).

Per-lab additional requirements:
- **Lab 5**: outbound HTTPS to `githubstatus.com` from Serverless compute.
- **Lab 6**: Vector Search endpoint, `databricks-gte-large-en` embedding endpoint.
- **Lab 7**: Lakebase access (or use the in-memory fallback).
- **Lab 8**: Unity Catalog catalog (Prompt Registry entries are scoped to UC).
- **Lab 9**: no external resources -- pure prompt-driven specialists.

## When to move on

After Lab 9, you'll have a multi-agent support coordinator that works end-to-end. [L300 Advanced](../l300-advanced/) covers two more production patterns: **Lab 10 -- Instructed Retrieval** (decomposition + multi-stage rerank) and **Lab 11 -- Genie Context-Aware Caching** (L1 LRU + L2 similarity over a Genie tool).
