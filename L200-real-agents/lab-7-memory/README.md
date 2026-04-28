# Lab 7 -- Persistent Memory

**Level:** L200

## Goals

- Configure a Lakebase-backed `memory.checkpointer:` for thread-scoped state that survives restarts.
- Add a `memory.store:` + `memory.extraction:` so structured facts persist across threads for the same `user_id`.
- Verify the agent recalls a customer's prior context across a brand-new thread.
- Add `app.chat_history:` so long conversations get summarized automatically once they exceed the token budget.

## Deliverable

A `saas-helpdesk-<your-username>` agent where Jordan opens a new thread and the agent recalls the prior issue (e.g. *"You were investigating a 401 error -- did that resolve?"*), and a long thread that triggers chat-history summarization mid-conversation.

---

**Use case:** `saas_helpdesk` -- a support assistant that remembers customer context across turns and across sessions, and that compresses long conversations on its own.

**DAO-AI concept:** **Memory** in two layers, plus chat-history summarization.

- **`memory.checkpointer:`** -- short-term, scoped to a `thread_id`. Persists the message history; survives notebook/app restarts.
- **`memory.store:` + `memory.extraction:`** -- long-term, scoped to a `user_id`. The extraction pipeline writes structured facts (name, recurring issues, preferences) into the store, and `auto_inject: true` injects them into the prompt on subsequent turns.
- **`app.chat_history:`** -- once the message history exceeds `max_tokens_before_summary`, DAO-AI uses a small/fast LLM to compress older turns into a single summary message. Recent turns stay verbatim. Token budgets stop blowing up.

All persistence is backed by Databricks **Lakebase** (managed Postgres).

## Files

| File | Purpose |
|---|---|
| `support_assistant.yaml` | The full agent config -- Lakebase memory + summarization, in one file. |
| `notebook.py` | Walk through the YAML, test cross-thread recall, then trigger summarization on a long thread. Deploy. |

## Prerequisites

- Lakebase access (workshop default: `retail-consumer-goods` instance).
- `databricks-claude-sonnet-4-5` (default LLM), `databricks-gpt-oss-120b` (memory query LLM), and `databricks-gpt-5-nano` (summarization LLM) foundation-model endpoints enabled.

## Run

Open `notebook.py`. Set the Lakebase widgets if your instance differs from the default. The notebook deliberately sets `max_tokens_before_summary` low (1500) so summarization fires within ~7 demo turns; production defaults are 6000 / 2048.

Deployed app name: `saas-helpdesk-<your-username>`.

## Next

[Lab 8](../lab-8-prompts-guardrails/) -- managed prompts in MLflow + an accuracy guardrail that retries on hallucination.
