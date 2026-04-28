# Lab 5 -- External Integrations via REST

**Level:** L200

## Goals

- Use `dao_ai.tools.create_rest_api_tool` to wrap a public HTTP endpoint as an agent tool.
- Switch domain framing from hardware-store retail to a SaaS support helpdesk.
- See how a support agent can triage upstream-vendor outages by calling a real status API.

## Deliverable

A `status-check` agent that answers `"Is GitHub having an outage right now?"` by calling `https://www.githubstatus.com/api/v2/status.json`.

---

**Use case:** **(switch to)** `saas_helpdesk` -- a tier-1 support agent that triages incoming issues. The chapter introduces the `status_check` agent that calls the public GitHub Status API to check whether a common upstream is degraded.

> Why switch use cases? The hardware-store retail story is great for product lookups (chapters 1-4). The remaining DAO-AI features -- vector search over knowledge bases, customer history memory, accuracy guardrails, tier-escalation orchestration -- are most natural in an internal-ops context. We start fresh so each chapter's config stays small and focused on the new feature.

**DAO-AI concept:** **REST tools via factory.** `dao_ai.tools.create_rest_api_tool` wraps any HTTP endpoint as a callable tool the agent can invoke.

## What you'll learn

- How to declare an HTTP factory tool with `base_url`, `name`, and `description`.
- That credential-free public APIs (like GitHub's `/api/v2/status.json`) are workshop-grade -- in production swap to a UC Connection for governed access.
- How a support triage agent uses upstream status to scope a customer's reported issue.

## Files

| File | Purpose |
|---|---|
| `status_check.yaml` | One agent, one REST tool calling `https://www.githubstatus.com`. |
| `notebook.py` | Build, test, deploy. |

## Prerequisites

- `databricks-claude-sonnet-4-5` foundation-model endpoint enabled.
- Network egress to `githubstatus.com` from Serverless compute (default-allowed).

## Run

Open `notebook.py`. No catalog needed.

Deployed app name: `saas-helpdesk-<your-username>`.

## Next

[Lab 6](../lab-06-vector-search/) -- vector search + reranking over a knowledge-base table for fuzzy support questions.
