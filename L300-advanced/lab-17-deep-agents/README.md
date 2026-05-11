# Lab 17 -- Deep Agent Orchestration

**Level:** L300 (advanced)

## Goals

- Configure dao-ai's new `orchestration.deep_agent:` block (added in dao-ai 0.1.73) alongside the existing supervisor / swarm patterns.
- Register a first-class **Skill** under `resources.skills:` — a directory containing at minimum a `SKILL.md` that teaches the planning agent how to do a task.
- Use **`deep_agent.instruction_files:`** to load `AGENTS.md`-style content into the system prompt at startup.
- Register a sub-agent and let the deep agent delegate to it via the built-in `task` tool.
- Verify inference in-notebook — no Databricks Apps / Model Serving deployment required for validation.

## Deliverable

A compiled `deep-research-<your-username>` agent that, given a research question, decomposes it via the bundled research skill, optionally delegates condensation to the `summarizer` sub-agent, and returns a structured multi-paragraph report. Inference runs in-notebook against the compiled LangGraph; an optional Step 7 walks through deploying to Model Serving.

---

**Use case:** Deep-research assistant that plans before answering, leans on a reusable Skill for methodology, and can delegate sub-tasks.

**DAO-AI concept:** `orchestration.deep_agent:` (new in 0.1.73) wrapping `deepagents.create_deep_agent`. Pulls together three new primitives:

| concept | dao-ai field | description |
|---|---|---|
| Deep Agent | `orchestration.deep_agent` | single planning agent built on `deepagents.create_deep_agent` — built-in `todo` / `filesystem` / `shell` / `task` tools |
| Skills | `resources.skills.<name>` | reusable directory of Markdown that teaches the agent how to do a task |
| Instruction files | `deep_agent.instruction_files` | `AGENTS.md`-style content loaded into the system prompt at startup |
| Sub-agents | `deep_agent.subagents` | agents callable via the built-in `task` tool |

## What you'll learn

- How `orchestration.deep_agent:` fits alongside `supervisor:` and `swarm:` (mutually exclusive — pick one orchestration pattern per app).
- Why a Skill is a *directory* of Markdown rather than a string prompt: the agent loads `SKILL.md` plus any supporting files at runtime, so you can keep large bodies of methodology / examples / templates outside the prompt.
- How `code_paths:` bundles local skill directories with the model artifact. (For governed deployments swap a local string for a `VolumePathModel` to read the skill from a UC volume.)
- The difference between `instruction_files` (static, baked into the system prompt at startup) and `OrchestrationModel.memory` (runtime checkpointer / store).
- Why deep agents can run a single agent — unlike supervisor / swarm which need ≥2.

## Files

- `deep_research.yaml` — config: `parameters`, two `llms`, one `skills` entry, two agents (`summarizer` sub-agent + `researcher` deep agent), and the new `orchestration.deep_agent:` block.
- `skills/research/SKILL.md` — bundled research methodology skill (decompose → plan → draft → synthesize).
- `instructions/AGENTS.md` — behavioral guidance loaded into the system prompt.
- `notebook.py` — install / params / inspect-config / compile / inference / structural-marker assertions / optional deploy.

## Prerequisites

**None** beyond workspace defaults. The lab is self-provisioning — it needs only the configured LLM serving endpoint (default `databricks-claude-sonnet-4-5`, available in every Databricks workspace). No catalogs / schemas / tables / volumes / Lakebase required.

## Run

Open `notebook.py` on Serverless compute. Run cell by cell. Watch:

1. **Step 1** — installs `dao-ai>=0.1.73` (earlier versions reject the `deep_agent` key).
2. **Step 3 (inspect config)** — dumps the `orchestration.deep_agent` block so you can see the new shape.
3. **Step 4 (compile)** — `config.as_responses_agent()` builds the LangGraph from the deep_agent config and prints the resolved Skills / sub-agents / instruction files.
4. **Step 5 (inference)** — runs `agent.predict(...)` against a hardware-store-category research question. The deep agent decomposes the question with the `todo` tool, optionally `task`-delegates condensation to `summarizer`, then synthesizes a structured response.
5. **Step 6 (assert markers)** — verifies the bundled skill loaded by checking for executive-summary / bullets / open-questions markers in the response.
6. **Step 7 (optional deploy)** — commented out by default. Uncomment to log a new model version via `create_agent()` and deploy to Model Serving via `deploy_agent()`.

## Next

You've now seen every dao-ai orchestration option: supervisor (Lab 9), swarm (Lab 9), and deep_agent (this lab). For visual configuration of all three patterns, use **dao-ai-builder** — Resources → Skills, then Application → Orchestration → Deep Agent.

Open questions to explore on your own:
- Swap the local `research_skill` for a UC-volume-backed skill. Compare governance posture.
- Add `permissions:` to lock the agent's filesystem tools to `/tmp/**`.
- Add a second sub-agent (e.g. a `critic`) and watch the deep agent decide when to delegate to which.
