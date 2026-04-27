# Lab 12 -- Programmatic Construction

**Level:** L300 (advanced)

## Goals

- Construct an `AppConfig` entirely in Python using `LLMModel`, `AgentModel`, `AppModel`, and `OrchestrationModel` -- no YAML file involved.
- Verify that YAML-loaded and Python-constructed configs produce structurally identical objects.
- Show when Python construction wins (dynamic agent generation, tests, embedding DAO-AI inside a larger application).

## Deliverable

A `programmatic-<your-username>` agent built end-to-end from Python that compiles via `as_graph()` and deploys via `config.deploy_agent()` -- structurally identical to its YAML-driven counterpart.

---

**Use case:** any -- this lab is concept-only. It demonstrates the alternate construction path that the rest of the workshop deliberately keeps in YAML.

**DAO-AI concept:** the in-memory `AppConfig` object model is the same target whether you load it from YAML or build it from Python. Pick whichever fits your workflow.

## When to use which

| Approach | Best for |
|----------|----------|
| **YAML** | Production agents, team review, config-as-code, non-developer edits |
| **Python** | Dynamic generation (one agent per tenant), tests, embedding DAO-AI in an existing Python app |

Both approaches produce the same `AppConfig` object. You can start with YAML and override fields in Python, or generate the whole config programmatically -- they round-trip cleanly.

## Walk-through

Open `notebook.py` on Databricks Serverless v5 and run cell by cell.

1. **Step 1 -- Install dependencies.** `%pip install "dao-ai>=0.1.59"` and restart.
2. **Step 2 -- Build an agent in pure Python.** Construct `LLMModel`, `AgentModel`, and `AppConfig` directly. No YAML file is read. `config.as_graph()` compiles the agent exactly as it would from a YAML-loaded config.
3. **Step 3 -- Invoke.** `await agent.ainvoke(...)` sends a test message and prints the reply.
4. **Step 4 -- Compare.** The notebook ends with a note on when YAML vs. Python is the right call.

## Deploy

The `AppConfig` object has the same deploy capabilities as a YAML-loaded one:

```python
config.deploy_agent()  # routes to Apps because deployment_target=APPS
```

## Key takeaways

- YAML and Python are interchangeable entry points to the same `AppConfig` object model. Pick whichever fits your workflow.
- Dynamic agent generation (one per tenant, one per dataset) is the primary reason to go programmatic.
- Mixing approaches is safe: load from YAML, then override fields in Python before calling `as_graph()`.

## Back to the workshop

[Workshop README](../../README.md) | [L300 Advanced](../README.md)
