# Lab 18 -- Skills-only Deep Agent

**Level:** L300 (advanced)

## Goals

- Configure a dao-ai deep_agent with **zero top-level agents** and **zero sub-agents** — only a Skill + system prompt.
- Verify dao-ai's `app.agents: []` carve-out under the deep_agent orchestration pattern (introduced in dao-ai 0.1.73+).
- Run in-notebook inference against the compiled deep agent and confirm the planner uses the bundled `code_review` skill.

## Deliverable

A compiled `code-reviewer-<your-username>` agent that produces a senior-engineer-style code review for an input snippet, using a single Skill as its methodology. No sub-agent delegation. No top-level agent definitions in the config.

---

## When to choose skills-only over agents+sub-agents

| pattern | use when |
|---|---|
| **Lab 17** — deep_agent + sub-agents | You need delegation to a *different* persona / model (e.g. a tight summarizer that runs cheaper than the planner) |
| **Lab 18** — deep_agent + skills-only | You're building a single specialist (code reviewer, bug triager, release-notes author, API critic, …) and the planner can do all the work itself |

## What this lab confirms

dao-ai's `AppModel.validate_agents_not_empty` model_validator (`config.py:6531-6540`) explicitly allows `app.agents: []` **only when** `orchestration.deep_agent` is set. Supervisor / swarm / no-orchestration still require at least one agent. This lab exercises the carve-out end-to-end.

| concept | dao-ai field | description |
|---|---|---|
| Deep Agent (no sub-agents) | `orchestration.deep_agent` | the planning agent IS the orchestration block |
| Skills | `resources.skills.<name>` | reusable directory of Markdown that teaches the agent how to do a task |
| Instruction file | `deep_agent.instruction_files` | `AGENTS.md`-style behavioral guidance loaded into the system prompt |
| **Empty agents list** | `app.agents: []` | allowed under deep_agent — the planner has no peers |

## Files

- `code_reviewer.yaml` — config with `app.agents: []`, one `resources.skills` entry, one `orchestration.deep_agent` block (no `subagents:`).
- `skills/code_review/SKILL.md` — review methodology (inventory → triage → draft → synthesize).
- `instructions/AGENTS.md` — behavioral guidance (be specific, terse, ask before asserting).
- `notebook.py` — install / parameterize / inspect-config / compile / inference / soft signals / optional negative test.

## Prerequisites

**None** beyond workspace defaults. Self-provisioning. Needs only the configured LLM serving endpoint (default `databricks-claude-sonnet-4-5`, available in every Databricks workspace). No catalogs / schemas / tables / volumes / Lakebase required.

## Run

Open `notebook.py` on Serverless compute. Run cell by cell. Watch:

1. **Step 1** — installs `dao-ai>=0.1.87`.
2. **Step 3 (inspect config)** — dumps the empty `app.agents` list and the deep_agent block with `skills:` but no `subagents:`.
3. **Step 4 (compile)** — `AppConfig.from_file()` triggers `validate_agents_not_empty`. The carve-out lets it pass.
4. **Step 5 (inference)** — submits a 10-line Python snippet for review. The planner uses the bundled `code_review` skill to produce a structured review.
5. **Step 6 (assertions)** — hard-fails only on empty `response.output`; surfaces soft signals (verdict word, concern categories, quoted code) for the facilitator.
6. **Step 7 (optional negative test)** — commented out by default. Uncomment to confirm that removing `orchestration.deep_agent` while keeping `app.agents: []` is correctly rejected by dao-ai's validator.

## Next

- See Lab 17 for the deep_agent pattern with a sub-agent.
- Try composing multiple skills (add a second directory under `skills/` and reference it under `deep_agent.skills`).
- Promote a local skill to UC governance by replacing the `path:` string with a `VolumePathModel` (`volume:` + `path:`).
