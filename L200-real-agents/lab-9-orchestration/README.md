# Lab 9 -- Multi-agent Orchestration

**Level:** L200

## Goals

- Declare three specialist agents (`tier1_support`, `tier2_engineer`, `escalation_lead`) with distinct prompts and `handoff_prompt:` strings.
- Wire them under a **supervisor** that routes per turn, then under a **swarm** with mixed deterministic + agentic handoffs.
- See how the same specialists work under both orchestration patterns.

## Deliverable

A `tier-routing` app where a refund question routes to escalation, a 500-error question routes to tier-2, and a how-to question routes to tier-1 -- all from one user input each.

---

**Use case:** `saas_helpdesk` -- the final chapter ties customer-routing into three specialists: `tier1_support`, `tier2_engineer`, and `escalation_lead`.

**DAO-AI concept:** **Two orchestration patterns** with the same specialists:
- **Supervisor** -- a router LLM picks the specialist per turn.
- **Swarm with directed routes** -- a triage agent deterministically hands off; specialists hand off to each other via agentic (LLM-decided) handoffs.

## What you'll learn

- How to declare multiple agents in `agents:` with distinct `prompt:` and `handoff_prompt:` fields.
- The `app.orchestration.supervisor:` block (router LLM + routing rubric).
- The `app.orchestration.swarm:` block with `default_agent` and `handoffs:` map (mixing `is_deterministic: true` and agentic handoffs).
- When a supervisor wins (predictability, clear routing) vs. a swarm (cheaper at runtime, more flexible flows).

## Files

| File | Purpose |
|---|---|
| `specialists_with_supervisor.yaml` | Supervisor pattern (default deploy). |
| `specialists_with_swarm.yaml` | Swarm pattern with mixed deterministic + agentic handoffs. |
| `notebook.py` | Build both, test routing for tier-1 / tier-2 / escalation scenarios. |

## Prerequisites

- `databricks-claude-sonnet-4-5` foundation-model endpoint enabled.
- No catalog or external resources required (these specialists are prompt-driven).

## Run

Open `notebook.py`. The notebook walks both patterns side by side.

Deployed app name: `tier-routing-<your-username>`.

## Next

[Lab 10 -- Human in the Loop](../lab-10-hitl/) -- gate the refund tool with `human_in_the_loop:` and resume the workflow on a human's approve / edit / reject decision.
