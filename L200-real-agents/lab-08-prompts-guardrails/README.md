# Lab 8 -- Production Prompts and Guardrails

**Level:** L200

## Goals

- Move an inline prompt into a reusable `PromptModel` via the `prompts:` block.
- Reference the shared prompt from the agent so the prompt text lives in one place.
- Add a `guardrails:` block with a judge LLM that evaluates response **accuracy** and retries on failure.
- Inspect nested guardrail spans in the MLflow trace.

## Deliverable

A `safe-support` agent that, when asked for a critical-ticket SLA it doesn't know, says so honestly instead of inventing one -- with a `accuracy_check` span visible in the trace.

---

**Use case:** `saas_helpdesk` -- a `safe_support` agent whose prompt is defined as a reusable object and whose responses are evaluated for **accuracy** by a judge LLM.

**DAO-AI concept:** Two production capabilities, one chapter:
1. **Reusable Prompts** -- define a prompt once in the `prompts:` block and reference it from any agent, keeping long prompt bodies out of the agent definition.
2. **Guardrails** -- a judge LLM evaluates each response and the agent retries on failure. For SaaS support, accuracy matters more than tone -- making up an SLA is worse than being a little dry.

## What you'll learn

- The `prompts:` top-level block and the `template:` field.
- The `guardrails:` top-level block (`model`, `prompt`, `num_retries`).
- How an accuracy-focused guardrail differs from a tone-focused one.
- Cost implications: at `num_retries: 2` a single user message can trigger up to 3 main LLM calls + 3 judge LLM calls.

## Files

| File | Purpose |
|---|---|
| `01_inline_support.yaml` | Step 1 -- inline prompt, no guardrail. |
| `02_support_with_managed_prompts.yaml` | Step 2 -- prompt as a reusable `PromptModel`. |
| `03_support_with_guardrails.yaml` | Step 3 (final / deploy) -- + accuracy guardrail. |
| `notebook.py` | Walk steps; observe reusable-prompt + guardrail behavior. |

## Prerequisites

- `databricks-claude-sonnet-4-5` foundation-model endpoint enabled.

## Run

Open `notebook.py`. Set `catalog` widget. Step 2 shows the agent referencing a shared prompt object.

Deployed app name: `saas-helpdesk-<your-username>`.

## Next

[Lab 9](../lab-09-orchestration/) -- multi-agent orchestration with tier-1 / tier-2 / escalation specialists.
