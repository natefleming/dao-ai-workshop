# Anatomy of a DAO-AI Config

> Lecture · L100 Foundations · 15 min read

A DAO-AI config is one YAML file. The `AppConfig` Python object loads from it, validates it, and turns it into a runnable LangGraph agent at one end and a deployable Databricks App at the other. This lecture walks the **shape** of that file -- every top-level section you'll meet across the workshop, when each one shows up, and how they reference each other.

```yaml
parameters:    # 1.  Declared inputs substituted into the rest of the YAML at load time.
variables:     # 2.  Reusable values pulled from env, secrets, literals, or first-of-many.
schemas:       # 3.  Catalog/schema shorthand reused everywhere.
resources:     # 4.  Physical things: LLMs, vector stores, warehouses, databases, ...
tools:         # 5.  Things an agent can call: UC functions, REST APIs, MCP, factory tools.
retrievers:    # 6.  Vector + rerank pipelines that back search-style tools.
prompts:       # 7.  Inline strings or MLflow Prompt Registry references.
guardrails:    # 8.  Input/output checks (judge LLM, GuardrailsAI hub).
memory:        # 9.  Checkpointer + store + extraction for cross-session state.
agents:        # 10. Agent definitions: model + prompt + tools + handoff hints.
app:           # 11. Deployable: which agents, orchestration, deployed app name.
```

Not every config uses all of these. Lab 1 needs only `parameters` + `resources` + `agents` + `app`. Each lab from there adds one or two more sections. By the time you reach the L300 advanced labs, the same shape covers everything from a single LLM up to a multi-agent swarm with vector search, memory, prompts, guardrails, and human-in-the-loop approvals.

## 1. `parameters:` -- variables for the YAML

Anything you'd pass at deploy time -- catalog name, username, LLM endpoint, Genie Space ID -- goes here. Each entry has a description and an optional default.

```yaml
parameters:
  username:
    description: Per-student suffix for unique deployment names.
    # No default => required at load time.
  catalog:
    description: Unity Catalog catalog containing workshop assets.
  llm_endpoint:
    description: Databricks LLM serving endpoint name.
    default: databricks-claude-sonnet-4-5
```

You reference parameters inline with `${var.NAME}` (or the equivalent `${param.NAME}`):

```yaml
schemas:
  workshop_schema:
    catalog_name: ${var.catalog}
    schema_name: dao_ai
```

You supply values when you load the config:

```python
from dao_ai.config import AppConfig
config = AppConfig.from_file("greeter.yaml", params={
    "username": "jane-doe",
    "catalog": "workshop_jane_doe",
})
```

Resolution order per reference: `params={}` you pass in → process env var (e.g. `CATALOG`) → declared `default:` → inline `${var.NAME:-fallback}` → **error**. The substituted YAML text is what gets shipped to the deployed app, so per-student values are baked in at deploy time.

**Inline fallback shorthand:** `${var.schema:-dao_ai}` yields `dao_ai` if no value resolves. Useful for optional knobs without cluttering `parameters:` defaults.

## 2. `variables:` -- reusable runtime values

`parameters:` is a load-time text substitution. `variables:` is a structured runtime concept: each entry is a typed value that knows how to resolve itself when the agent runs. Four kinds, all addressable by anchor:

```yaml
variables:
  # 2a. Read from a process env var (with a fallback default).
  client_id: &client_id
    env: SUPPORT_CLIENT_ID
    default_value: ""

  # 2b. Read from a Databricks secret scope.
  api_token: &api_token
    scope: workshop
    secret: github_status_token

  # 2c. A literal constant (string, int, float, or bool).
  default_temperature: &default_temperature
    value: 0.1

  # 2d. Composite: try options in order, return the first non-None.
  workspace_host: &workspace_host
    options:
      - env: DATABRICKS_HOST
      - scope: workshop
        secret: workspace_host
      - "https://my-workspace.cloud.databricks.com"
```

Use them anywhere a typed `AnyVariable` field is accepted -- REST tool headers, service-principal `client_id` / `client_secret`, OBO workspace hosts, etc.:

```yaml
tools:
  github_status:
    function:
      type: rest
      base_url: https://api.github.com
      headers:
        Authorization: *api_token   # pulled from secret scope at runtime
```

**`parameters:` vs `variables:` rule of thumb:**

- `parameters:` is for things that *change the YAML's literal text* at load time -- catalog name, username, LLM endpoint name. Substituted into any string. Resolved once before validation.
- `variables:` is for *runtime values* the agent dereferences when it actually needs them -- secrets that shouldn't be in YAML text, env vars that change per environment, multi-source fallbacks. Resolved on each access.

If you find yourself baking a secret into a parameter, switch to a variable. If you find yourself wiring an env var through a variable just so the YAML text reads the right way, switch to a parameter.

## 3. `schemas:` -- catalog/schema shorthand

A tiny convenience block that gives `${var.catalog}.${var.schema}` a name you can alias and reuse.

```yaml
schemas:
  workshop_schema: &workshop_schema
    catalog_name: ${var.catalog}
    schema_name: ${var.schema}
```

Anywhere you need that schema (UC functions, datasets, vector store source tables, ...) you write `*workshop_schema` instead of duplicating the two fields.

## 4. `resources:` -- physical dependencies

Resources are the Databricks (or external) objects the agent talks to. Declared once, referenced by anchor wherever they're used.

```yaml
resources:
  llms:
    default_llm: &default_llm
      name: ${var.llm_endpoint}
      temperature: 0.1
      max_tokens: 4096

  vector_stores:
    kb_vs: &kb_vs
      embedding_model: { name: databricks-gte-large-en }
      endpoint: { name: dao_ai_workshop_vs }
      index: { schema: *workshop_schema, name: kb_articles_index }
      source_table: { schema: *workshop_schema, name: kb_articles }
      primary_key: article_id
      embedding_source_column: body
      on_behalf_of_user: true            # ← run searches as the calling user
```

Resource types you'll meet across the workshop:

| Resource | First lab | Purpose |
|---|---|---|
| `llms` | Lab 1 | Foundation-model serving endpoints |
| `functions` | Lab 2 | Unity Catalog SQL functions |
| `genie_rooms` | Lab 3 | Databricks Genie Space |
| `vector_stores` | Lab 6 | Delta-Sync vector index over a Delta table |
| `databases` | Lab 7 | Lakebase (managed Postgres) for memory |
| `warehouses` | Lab 12 | SQL warehouse (cache replay, OBO queries) |

Every resource type accepts an `on_behalf_of_user: true` flag. With it, calls go out using the caller's identity (Databricks Apps forwards `x-forwarded-access-token`; Model Serving uses `ModelServingUserCredentials`) instead of the app's service principal -- so per-user UC permissions actually apply at query time.

The `&default_llm` and `&kb_vs` are YAML **anchors**: name a block once with `&name`, reuse it later with `*name`. DAO-AI configs lean on anchors heavily to keep things DRY.

## 5. `tools:` -- what an agent can call

Tools wrap the resources. There are four shapes you'll see, all interchangeable from the agent's point of view:

```yaml
tools:
  # 5a. Unity Catalog SQL function as a tool.
  find_product_by_sku: &find_product_by_sku
    name: find_product_by_sku
    function:
      type: unity_catalog
      schema: *workshop_schema
      name: find_product_by_sku

  # 5b. Schema-wide tool discovery via a managed MCP server.
  functions_mcp: &functions_mcp
    name: functions_mcp
    function:
      type: mcp
      functions: *workshop_schema       # exposes every UC function in the schema

  # 5c. Factory tool: a Python callable that builds the tool object.
  kb_search: &kb_search
    name: kb_search
    function:
      type: factory
      name: dao_ai.tools.create_vector_search_tool
      args:
        retriever: *kb_retriever
        name: kb_search
        description: Semantic search over the support KB.

  # 5d. REST tool: declarative HTTP integration.
  github_status: &github_status
    name: github_status
    function:
      type: rest
      base_url: https://www.githubstatus.com
      endpoints:
        - name: get_summary
          path: /api/v2/summary.json
          method: GET
```

UC and Genie tools are the most governed (typed parameters, audit trail in UC). MCP gives you schema-wide discovery without re-listing every function. Factory tools are how vector search, reranking, Genie caching, etc. plug in. REST is the escape hatch for anything outside Databricks.

## 6. `retrievers:` -- the search pipelines behind tools

A retriever is a multi-stage search recipe: ANN search, optional cross-encoder rerank, optional LLM-based instruction rerank, optional query decomposition. The factory tool above (`dao_ai.tools.create_vector_search_tool`) just wraps a retriever.

```yaml
retrievers:
  kb_retriever: &kb_retriever
    vector_store: *kb_vs
    columns: [article_id, title, topic, body]
    search_parameters:
      num_results: 50                  # wide net for recall
      query_type: HYBRID
    rerank:
      model: ms-marco-MiniLM-L-12-v2   # FlashRank cross-encoder
      top_n: 5                         # narrow to top 5 for precision
```

Lab 11 adds an `instructed:` block on top -- `decomposition:` (LLM splits the query into filters + residual semantic query) and an LLM-based `rerank:` that follows natural-language instructions.

## 7. `prompts:` -- inline or registry-managed

Simplest case: prompt as an inline string on the agent.

```yaml
agents:
  support_agent:
    prompt: |
      You are tier-1 support. Answer factually...
```

Production case: pull from MLflow's Prompt Registry by name + version, so prompt changes ship without redeploying the agent.

```yaml
prompts:
  support_v1: &support_v1
    type: registry
    name: ${var.catalog}.${var.schema}.support_assistant
    version: 1

agents:
  support_agent:
    prompt: *support_v1
```

Lab 8 walks the inline → registry path step by step.

## 8. `guardrails:` -- input/output checks

Guardrails sit on the input or output of an agent. Two flavors:

```yaml
guardrails:
  # 7a. Judge-LLM guardrail: a separate LLM rates the answer; agent retries on fail.
  accuracy_judge: &accuracy_judge
    type: judge
    model: *default_llm
    prompt: |
      Rate the assistant's answer for factual accuracy 1-5.
      Respond with just the number.
    threshold: 4
    max_retries: 2

  # 7b. GuardrailsAI hub validator (toxic language, PII, etc.).
  no_pii: &no_pii
    type: hub
    name: detect-pii
```

Attach to an agent (or to the app) under `guardrails:`. Lab 8 does both.

## 9. `memory:` -- cross-session state

Three sub-blocks, each independent:

```yaml
memory:
  checkpointer:                          # short-term: thread-scoped state survives restarts
    name: support_checkpointer
    database: *workshop_db
  store:                                 # long-term: facts persist across threads
    name: support_store
    database: *workshop_db
    namespace: "{user_id}"               # one namespace per user
  extraction:                            # background pipeline that mines facts from chats
    schemas: [user_profile, preference]
    auto_inject: true
```

The checkpointer is what makes a thread resumable. The store is what makes "do you remember what we discussed last week?" work across thread boundaries. The extraction pipeline writes structured facts into the store automatically. Lab 7 covers all three.

## 10. `agents:` -- agent definitions

An agent ties together a model, a prompt, an optional set of tools, and an optional `handoff_prompt:` (used by supervisor / swarm orchestration to decide when to route to this agent).

```yaml
agents:
  tier1_support: &tier1_support
    name: tier1_support
    description: Front-line triage agent.
    model: *fast_llm
    tools:
      - *kb_search
    prompt: |
      You are tier-1 support. Classify the customer's question.
    handoff_prompt: |
      How-to questions, account questions, simple policy lookups.
```

Multiple agents are first-class: declare them all here and let `app.orchestration` decide who gets to talk when.

## 11. `app:` -- the deployable

The deployable shape: which agents are in the deployment, how they're wired together, what the deployed app is called.

```yaml
app:
  name: tier-routing-${var.username}
  description: "Multi-tier support routing"
  deployment_target: apps                  # apps | model_serving
  agents:
    - *tier1_support
    - *tier2_engineer
    - *escalation_lead
  orchestration:
    supervisor:                            # one of: swarm, supervisor
      model: *default_llm
      prompt: |
        Route the customer to the right specialist.
  chat_history:                            # optional: auto-summarize long threads
    model: *summarization_llm
    max_tokens: 2048
    max_tokens_before_summary: 6000
  input_example:
    messages:
      - role: user
        content: "I need a refund for the duplicate charge."
  environment_vars:                        # optional: app-startup env (secrets, etc.)
    SLACK_BOT_TOKEN:
      scope: workshop
      secret: slack_bot_token
```

`orchestration:` is **optional** -- when you have a single agent and no memory, the runtime treats the lone agent as the entry point automatically. You only need this block when you have multiple agents (`swarm` for "any agent can hand off to any other" or `supervisor` for "a router LLM picks per turn") **or** when you wire memory through `orchestration.memory` (Lab 7 / Lab 10). Lab 9 demos both `swarm` and `supervisor` back to back with the same three specialists.

`environment_vars:` is the one place you declare runtime env vars (or secret references) the deployed app needs at boot.

## A complete minimal config

Lab 1's `greeter.yaml` -- only sections 1, 3, 9, 10:

```yaml
parameters:
  username:
    description: Per-student suffix for unique deployment names.
  llm_endpoint:
    description: Databricks LLM serving endpoint name.
    default: databricks-claude-sonnet-4-5

resources:
  llms:
    default_llm: &default_llm
      name: ${var.llm_endpoint}
      temperature: 0.1
      max_tokens: 2048

agents:
  greeter: &greeter
    name: greeter
    description: A friendly assistant.
    model: *default_llm
    prompt: |
      You are the welcome agent. Greet the user warmly.

app:
  name: greeter-${var.username}
  deployment_target: apps
  agents: [*greeter]
  input_example:
    messages:
      - role: user
        content: "Hi!"
```

No `orchestration:` block -- with a single agent and no memory, none is needed. That's a real, deployable agent. Each L100/L200/L300 lab adds one new section to this skeleton and stops -- so by the end of the workshop you've assembled the whole anatomy in pieces.

## What's next

[**Lab 1 -- Your First DAO-AI Agent**](lab-1-first-agent/) -- run the config above end-to-end.
