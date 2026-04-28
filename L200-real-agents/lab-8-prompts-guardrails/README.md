# Lab 8 -- Production Prompts and Guardrails

**Level:** L200

## Goals

- Move an inline prompt into MLflow Prompt Registry via the `prompts:` block.
- Edit the prompt in the MLflow UI and watch the agent pick up the new version on next load.
- Add a `guardrails:` block with a judge LLM that evaluates response **accuracy** and retries on failure.
- Inspect nested guardrail spans in the MLflow trace.

## Deliverable

A `safe-support` agent that, when asked for a critical-ticket SLA it doesn't know, says so honestly instead of inventing one -- with a `accuracy_check` span visible in the trace.

---

**Use case:** `saas_helpdesk` -- a `safe_support` agent whose prompt lives in MLflow Prompt Registry and whose responses are evaluated for **accuracy** by a judge LLM.

**DAO-AI concept:** Two production capabilities, one chapter:
1. **MLflow Prompt Registry** -- prompts auto-register on first load and can be edited in the UI without redeploying.
2. **Guardrails** -- a judge LLM evaluates each response and the agent retries on failure. For SaaS support, accuracy matters more than tone -- making up an SLA is worse than being a little dry.

## What you'll learn

- The `prompts:` top-level block and how `default_template:` bootstraps version 1.
- The `guardrails:` top-level block (`model`, `prompt`, `num_retries`).
- How an accuracy-focused guardrail differs from a tone-focused one.
- Cost implications: at `num_retries: 2` a single user message can trigger up to 3 main LLM calls + 3 judge LLM calls.

## Files

| File | Purpose |
|---|---|
| `01_inline_support.yaml` | Step 1 -- inline prompt, no guardrail. |
| `02_support_with_managed_prompts.yaml` | Step 2 -- prompt in MLflow Registry. |
| `03_support_with_guardrails.yaml` | Step 3 (final / deploy) -- + accuracy guardrail. |
| `notebook.py` | Walk steps; observe registry + guardrail behavior. |

## Prerequisites

- A Unity Catalog catalog (Prompt Registry entries are scoped to UC).
- `databricks-claude-sonnet-4-5` foundation-model endpoint enabled.

## Run

Open `notebook.py`. Set `catalog` widget. After step 2 runs, open the **Prompts** tab in MLflow to see your auto-registered prompts.

Deployed app name: `saas-helpdesk-<your-username>`.

## Next

[Chapter 9](../lab-9-orchestration/) -- multi-agent orchestration with tier-1 / tier-2 / escalation specialists.
