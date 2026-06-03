# L300 -- Advanced

The third level of the DAO-AI workshop. L300 covers production-grade patterns that separate a working agent from a fast, accurate, scalable one, plus alternate construction paths and runtime contracts:

- **Lab 11 -- Instructed Retrieval.** Decompose natural-language queries into structured filter constraints, then layer cross-encoder + LLM-based reranking for precision. Pure ANN+rerank from Lab 6 isn't enough when users describe constraints (brand, price tier, project intent) inline.
- **Lab 12 -- Genie Context-Aware Caching.** Two-layer cache over a Genie tool: an L1 LRU exact-match cache and an L2 context-aware similarity cache. Cuts Genie API cost and latency dramatically for repeat / near-duplicate questions.
- **Lab 13 -- Programmatic Construction.** Build the same `AppConfig` in pure Python instead of YAML -- the entry point you reach for when generating agents dynamically (one per tenant, one per dataset) or embedding DAO-AI inside a larger Python application.
- **Lab 14 -- Custom-Input Validation.** Wire `dao_ai.middleware.create_custom_field_validation_middleware` into an agent so missing per-call context (`store_num`, `customer_tier`) returns a copy-paste-ready error before the model runs. Demonstrates the **input contract** dimension of production agents.
- **Lab 15 -- Long-Running / Background Agents.** `app.long_running:` block + Lakebase-backed responses store. Kickoff returns a `resp_*` ID immediately; the client polls `operation: retrieve` (or the deployed app's `/v1/responses/{id}` route) until `completed`. Demonstrates the **async lifecycle** dimension.
- **Lab 16 -- Declarative Genie Space Provisioning.** Provision a Genie space from pure YAML -- no agents, no app block. Exercises every `GenieRoomModel` field: table sources with column configs, metric view sources, UC function sources, text instructions, example SQLs with parameters, join specs, SQL snippets, sample questions, benchmarks, and entitlements.
- **Lab 17 -- Deep Agent Orchestration.** dao-ai 0.1.73+'s third orchestration option alongside supervisor / swarm. A single planning agent built on `deepagents.create_deep_agent` with built-in `todo` / `filesystem` / `shell` tools, first-class **Skills** (directory-of-Markdown methodology), `AGENTS.md`-style **instruction files**, and sub-agents callable via the `task` tool. Self-provisioning — no external resources required.
- **Lab 18 -- Skills-only Deep Agent.** The minimum viable deep_agent: zero top-level agents and zero sub-agents — only a Skill + system prompt. Exercises dao-ai's `app.agents: []` carve-out under the deep_agent pattern (`AppModel.validate_agents_not_empty` at `config.py:6531-6540`). Use this when you need a single specialist (code reviewer / bug triager / release-notes author) and the planner can do all the work itself.
- **Lab 19 -- A2A Protocol (Minimal).** Every dao-ai 0.1.80+ Apps deployment auto-mounts Google's A2A v0.3 endpoints (`GET /.well-known/agent-card.json` + JSON-RPC `POST /a2a`) alongside the existing OpenAI Responses contract. Use the native `a2a-sdk` Python client (`A2ACardResolver`, `A2AClient`) to discover the Agent Card + send a single `message/send` round-trip. Demonstrates how dao-ai auto-derives skills from `app.agents:` and emits a single PAT/M2M bearer scheme when no resource has OBO.
- **Lab 20 -- A2A Protocol: HITL + OBO.** Builds on Lab 19. Tag tools with `human_in_the_loop:` and the model's `default_llm` with `on_behalf_of_user: true`. Demonstrates how dao-ai's auto-OBO-derivation flips the Agent Card to BOTH `oauth2` (declarative authorization-code flow with `user_impersonation` scope and real workspace URLs) AND `bearer` (the wire shape the Apps proxy forwards). Shows the HITL contract over A2A: `state: input-required` with a DataPart payload, resumed by another `message/send` carrying `{"decisions": [{"type": "approve"}]}`. Closes with the SSE streaming variant via `A2AClient.send_message_streaming`.
- **Lab 21 -- User Feedback.** Read the outer multi-agent `trace_id` from `response.custom_outputs["trace_id"]` and attach thumbs-up / thumbs-down via `dao_ai.evaluation.log_user_feedback`. Verifies the assessment lands on the OUTER root trace (not a sub-agent leg) and queries assessments via `mlflow.search_traces` + Spark SQL.
- **Lab 22 -- Offline Evaluation with Judges and Datasets.** Run `mlflow.genai.evaluate()` against the Lab 21 supervisor with four progressively richer dataset/scorer combinations: (A) a dao-ai config-defined inline `EvaluationDatasetModel` plus `build_scorers(config.evaluation)`, (B) a UC Delta table wrapped as a managed MLflow dataset, (C) a custom `@scorer` returning `Feedback`, and (D) per-row guidelines via `ExpectationsGuidelines`.
- **Lab 23 -- Production Monitoring with Registered Scorers.** Declare an `app.monitoring` block (built-in scorers + named `Guidelines` judges + sample rates) and register the lifecycle via `dao_ai.evaluation.register_monitoring_scorers`. Drive traffic, then verify assessments land on the traces via `mlflow.search_traces` + `LATERAL VIEW EXPLODE(assessments)` SQL. Closes with `stop_monitoring_scorers()` cleanup.

Lab 11 and Lab 12 reuse the products catalog from Lab 2 (extended with metadata for Lab 11) and a Genie Space pointed at it (for Lab 12). Lab 13 is concept-only -- no extra resources required. Lab 14 reuses Lab 2's products table plus a tier-aware UC function. Lab 15 reuses Lab 7's Lakebase wiring. Lab 22 and Lab 23 reuse Lab 21's two-tier supervisor and add evaluation/monitoring config on top.

## Walk this level in order

| Step | Path | Type | What it covers |
|---|---|---|---|
| 1 | [lab-11-instructed-retrieval/](lab-11-instructed-retrieval/) | Lab | Filter-aware retrieval with decomposition + cross-encoder + LLM rerank. |
| 2 | [lab-12-genie-caching/](lab-12-genie-caching/) | Lab | L1 LRU + L2 similarity caching over a Genie tool. |
| 3 | [lab-13-programmatic/](lab-13-programmatic/) | Lab | Build the same `AppConfig` from Python instead of YAML. |
| 4 | [lab-14-custom-input-validation/](lab-14-custom-input-validation/) | Lab | Middleware-based validation of `custom_inputs.configurable`. |
| 5 | [lab-15-long-running/](lab-15-long-running/) | Lab | Responses-API kickoff/poll/cancel + Lakebase-persisted state. |
| 6 | [lab-16-genie-provisioning/](lab-16-genie-provisioning/) | Lab | Declarative Genie space provisioning from YAML. |
| 7 | [lab-17-deep-agents/](lab-17-deep-agents/) | Lab | Deep Agent orchestration (planning + skills + sub-agents). |
| 8 | [lab-18-skills-only-deep-agent/](lab-18-skills-only-deep-agent/) | Lab | Skills-only Deep Agent (zero top-level agents, zero sub-agents). |
| 9 | [lab-19-a2a-minimal/](lab-19-a2a-minimal/) | Lab | A2A protocol — Agent Card discovery + `message/send` via the native `a2a-sdk` client. |
| 10 | [lab-20-a2a-hitl-obo/](lab-20-a2a-hitl-obo/) | Lab | A2A protocol — HITL `input-required`/resume + auto-derived `oauth2`+`bearer` schemes from resource OBO. |
| 11 | [lab-21-feedback/](lab-21-feedback/) | Lab | User feedback on multi-agent responses. Read `custom_outputs["trace_id"]` and call `dao_ai.evaluation.log_user_feedback`. Verify the assessment lands on the OUTER root trace. |
| 12 | [lab-22-offline-evaluation/](lab-22-offline-evaluation/) | Lab | Offline evaluation with judges and datasets. Inline `EvaluationDatasetModel`, UC table -> managed MLflow dataset, custom `@scorer`, per-row guidelines via `ExpectationsGuidelines`. |
| 13 | [lab-23-production-monitoring/](lab-23-production-monitoring/) | Lab | Production monitoring with registered scorers. `app.monitoring` block + `register_monitoring_scorers` + SQL verification of trace assessments. |

## Prerequisites

L100 + L200 completed. You should be comfortable with:
- Loading DAO-AI configs with `AppConfig.from_file(path, params={...})`.
- Per-student deployment via `${var.username}` and `config.deploy_agent(target=DeploymentTarget.APPS)`.
- Lab 2 (UC tools) and Lab 6 (vector search + rerank) -- their data structures show up again here.
- Lab 7 (memory) -- Lakebase wiring is reused by Lab 15.

Lab-specific requirements:
- **Lab 11**: Vector Search endpoint, `databricks-claude-haiku-4-5` (decomposition + instruction rerank), `databricks-gte-large-en` (embedding).
- **Lab 12**: a Genie Space over the products table (Lab 3's space works), a SQL warehouse you can re-execute cached SQL on.
- **Lab 14**: a Unity Catalog catalog you can write to (the `catalog` widget). The notebook self-provisions schema, products table, UC function.
- **Lab 15**: same Lakebase / SP setup as Lab 7 (`setup/create_service_principal.py` + `setup/grant_lakebase_superuser.py` + the `retail-consumer-goods` Lakebase autoscaling project).
- **Lab 21**: no external resources -- self-contained two-agent supervisor.
- **Lab 22**: a UC catalog/schema you can write to (defaults to `main.dao_ai_workshop` -- override via widget). A judge LLM endpoint (defaults to `databricks-claude-sonnet-4-5`).
- **Lab 23**: same UC catalog/schema as Lab 22. Optional SQL warehouse ID widget for UC OTEL trace tables (lab works without it against experiment-resident traces).

## What you'll have at the end

A single Databricks App `hardware-store-<your-username>` that gets redeployed per lab:
- After **Lab 11**: handles filter-rich, intent-laden product queries.
- After **Lab 12**: serves repeat / near-duplicate analytical questions from cache.
- After **Lab 13**: same as Lab 4 but built in pure Python.
- After **Lab 14**: rejects requests missing required context, runs tier-aware lookups when context is supplied.
- After **Lab 15**: handles deep-research style requests asynchronously via Responses-API kickoff/poll/cancel.

Each lab's `app.description` updates so you can see which lab last deployed.

## Going deeper

- `dao-ai/config/examples/03_reranking/` -- more reranking recipes (instruction-aware reranking, hybrid stages).
- `dao-ai/config/examples/04_genie/` -- more cache patterns including the database-backed variant for multi-instance deployments, and a recipe for tuning cache hit-rate thresholds.
- `dao-ai/config/examples/15_complete_applications/` -- end-to-end production examples that combine many of these patterns.
