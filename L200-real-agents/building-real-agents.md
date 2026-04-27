# Building Real Agents

> Lecture · L200 Building Real Agents · 10 min read

L100 built a tool-using agent. That's enough to demo. It's not enough to ship.

This lecture frames what L200 adds. Each section maps to one of the five labs.

## What separates a demo from production

A production agent has to answer five questions that a demo doesn't.

### 1. "What about systems we don't own?" (Lab 5 -- REST)

Most useful tools live outside Databricks: a status API, a CRM, a payment processor, an internal microservice. DAO-AI's REST factory wraps any HTTP endpoint as a callable tool with one YAML block.

```yaml
tools:
  call_status_api:
    function:
      type: factory
      name: dao_ai.tools.create_rest_api_tool
      args:
        base_url: "https://www.githubstatus.com"
        name: check_github_status
        description: "Check GitHub's status."
```

Lab 5 calls a real public no-auth endpoint -- in production you'd swap to a UC Connection for governed credentials.

### 2. "How does it answer fuzzy questions?" (Lab 6 -- Vector Search)

Customers don't know your schema. They ask *"how do I rotate my API keys?"* not *"give me KB-001"*. Vector search over your knowledge base bridges the gap.

DAO-AI builds a Delta Sync vector index from your YAML, exposes it as a retriever, and wraps the retriever as a factory tool. Lab 6 also adds **cross-encoder reranking** for precision: ANN gives recall (50 candidates), FlashRank promotes the most relevant 5.

### 3. "Does the agent remember anything?" (Lab 7 -- Memory)

By default an agent treats every turn as the first. That's fine for stateless lookups; it's miserable for support, where customers expect you to remember their last ticket.

DAO-AI's `memory:` block has two layers:

- **Checkpointer** (short-term, scoped to a `thread_id`) -- the conversation history persists across notebook/app restarts.
- **Store + extraction** (long-term, scoped to a `user_id`) -- structured facts the LLM extracts from conversations are saved per user. Returning customers get their context back.

Both layers run on Databricks **Lakebase** (managed Postgres). Lab 7 walks all three states: stateless → thread → persistent.

### 4. "Is the answer trustworthy?" (Lab 8 -- Prompts + Guardrails)

Two production problems with one chapter:

- **Prompt drift.** Prompts hard-coded in YAML force a redeploy to change. **MLflow Prompt Registry** decouples them -- prompt engineers edit in the UI, the agent picks up the new version on next load.
- **Quality variance.** A judge LLM evaluates each response against a rubric. If it fails (the response invents a specific SLA, makes up a policy), the agent retries with the critique. For support, **accuracy** matters more than tone.

### 5. "How does one agent become a team?" (Lab 9 -- Orchestration)

Cramming every responsibility into one agent produces a bloated, unreliable prompt. The fix is multi-agent: tier-1 handles how-to questions, tier-2 handles bugs, escalation handles refunds.

DAO-AI supports two orchestration patterns:

- **Supervisor** -- a router LLM picks one specialist per turn based on each specialist's `handoff_prompt`.
- **Swarm with directed routes** -- the entry agent deterministically hands off after triage; specialists hand off to each other when context shifts. Mix deterministic and agentic handoffs in the same swarm.

Lab 9 builds both with the same three specialists.

## What stays the same from L100

Everything you learned in L100 still holds. You're still:

- Declaring `parameters:`, `resources:`, `agents:`, `app:` in YAML.
- Loading via `AppConfig.from_file(path, params={...})`.
- Deploying via `config.deploy_agent(target=DeploymentTarget.APPS)`.
- Using `${var.username}` to keep deployed names unique per student.

L200 just adds new top-level YAML keys (`memory:`, `prompts:`, `guardrails:`) and new resource types (`databases:`, `vector_stores:`). The composition pattern is identical.

## What's next

[**Lab 5 -- External Integrations via REST**](lab-5-rest/) -- the support agent's first L200 capability.
