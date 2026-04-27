# Anatomy of a dao-ai Config

> Lecture · L100 Foundations · 10 min read

Every dao-ai config has the same four top-level sections. The whole workshop is variations on this shape.

```yaml
parameters:    # Inputs that get substituted into the rest of the config at load time.
resources:     # Physical things the agent uses: LLMs, schemas, vector stores, databases, etc.
agents:        # The agent definitions: name, model, tools, prompt.
app:           # The deployable: which agents, how they're orchestrated, the deployed app name.
```

That's the whole framework surface for L100. L200 adds a few sibling top-level keys (`memory`, `prompts`, `guardrails`, `tools` declared separately) -- still the same pattern.

## 1. `parameters:` -- declared inputs

`parameters:` lists every value the rest of the YAML can reference via `${var.NAME}`. Each parameter has a description and an optional default.

```yaml
parameters:
  username:
    description: Per-student suffix for unique deployment names.
    # No default => required at load time.
  llm_endpoint:
    description: Databricks LLM serving endpoint name.
    default: databricks-claude-sonnet-4-5
```

When you load the config, you supply parameter values:

```python
from dao_ai.config import AppConfig
config = AppConfig.from_file("greeter.yaml", params={"username": "jane-doe"})
```

dao-ai substitutes `${var.username}` with `"jane-doe"` everywhere it appears.

**Why this matters in the workshop:** every lab uses `username` so each student's deployed app has a unique name. Most labs add `catalog`, `schema`, and other parameters specific to that lab.

## 2. `resources:` -- physical dependencies

Resources are the things outside dao-ai that the agent needs:

```yaml
resources:
  llms:
    default_llm: &default_llm
      name: ${var.llm_endpoint}
      temperature: 0.1
      max_tokens: 4096
```

The `&default_llm` is a YAML **anchor** -- a name you can reference later with `*default_llm` to avoid copying the whole block. dao-ai uses anchors heavily.

Other resource types you'll meet across the labs:

| Resource | Used in | Purpose |
|---|---|---|
| `llms` | every lab | Foundation-model endpoints |
| `functions` | Labs 2, 4 | Unity Catalog SQL functions |
| `genie_rooms` | Lab 3 | A Databricks Genie Space |
| `vector_stores` | Lab 6 | Vector Search index over a Delta table |
| `databases` | Lab 7 | Lakebase (Postgres) for memory |
| `warehouses` | Wrap | SQL warehouse for cache replay |

## 3. `agents:` -- the agents themselves

An agent ties together a model, a prompt, and an optional list of tools.

```yaml
agents:
  greeter: &greeter
    name: greeter
    description: A friendly assistant.
    model: *default_llm
    prompt: |
      You are a friendly assistant. Greet the user warmly.
```

Lab 1 has no tools -- just a prompt and a model. Lab 2 adds `tools: [*sku_lookup_tool, *category_lookup_tool]`. Lab 9 declares three agents and orchestrates them.

## 4. `app:` -- the deployable

`app:` is what gets deployed when you call `config.deploy_agent(...)`. It lists the agents in the deployment, the orchestration pattern, and the deployed app name.

```yaml
app:
  name: greeter-${var.username}        # ← parameter substitution
  description: "Workshop hello world"
  log_level: INFO
  deployment_target: apps              # ← deploy as a Databricks App
  agents:
    - *greeter                         # ← reference the agent declared above
  orchestration:
    swarm:
      default_agent: *greeter          # ← single-agent swarm = trivial routing
  input_example:
    messages:
      - role: user
        content: "Hi! Is this thing on?"
```

The `app.name` field is parameterized so each student's deployment is unique. The `orchestration:` block is trivial here (one agent, no real routing); Lab 9 expands it into supervisor and swarm patterns.

## A complete minimal config

Putting it together -- this is roughly Lab 1's `greeter.yaml`:

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
  orchestration:
    swarm:
      default_agent: *greeter
  input_example:
    messages:
      - role: user
        content: "Hi!"
```

That's a real, deployable agent. **In Lab 1 you'll load this with `AppConfig.from_file(...)`, run it locally, and deploy it as a Databricks App with one Python call.**

## What's next

[**Lab 1 -- Your First dao-ai Agent**](lab-1-first-agent/) -- run the config above end-to-end.
