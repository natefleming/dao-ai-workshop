# Sidebar -- Programmatic Construction

Build the same agent from Chapter 01 using the dao-ai Python object model instead of YAML. Not a numbered chapter -- use this after chapters 1-2 when students ask "can I do this in Python instead?"

## What you'll learn

- How to construct an `AppConfig` entirely in Python using `LLMModel`, `AgentModel`, `AppModel`, and `OrchestrationModel`
- That YAML-loaded and Python-constructed configs produce structurally identical objects
- When Python construction wins over YAML (dynamic generation, tests, embedding dao-ai in a larger application)

## When to use which

| Approach | Best for |
|----------|----------|
| **YAML** | Production agents, team review, config-as-code, non-developer edits |
| **Python** | Dynamic generation (one agent per tenant), tests, embedding dao-ai in an existing Python app |

Both approaches produce the same `AppConfig` object. You can start with YAML and override fields in Python, or generate the whole config programmatically -- they round-trip cleanly.

## Walk-through

Open `notebook.py` on Databricks Serverless v5 and run cell by cell.

1. **Step 1 -- Install dependencies.** `%pip install "dao-ai>=0.1.57"` and restart.
2. **Step 2 -- Build an agent in pure Python.** Construct `LLMModel`, `AgentModel`, and `AppConfig` directly. No YAML file is read. `config.as_graph()` compiles the agent exactly as it would from a YAML-loaded config.
3. **Step 3 -- Invoke.** `await agent.ainvoke(...)` sends a test message and prints the reply.
4. **Step 4 -- Compare.** The notebook ends with a note on when YAML vs. Python is the right call.

## Deploy

The `AppConfig` object has the same deploy capabilities as a YAML-loaded one:

```python
config.deploy_agent()  # routes to Apps because deployment_target=APPS
```

Or generate a bundle from Python and deploy via CLI:

```bash
# From 98-programmatic/
dao-ai generate-bundle -c dao_ai.yaml -o . --force -p <profile>
databricks bundle deploy -t dev -p <profile>
```

## Key takeaways

- YAML and Python are interchangeable entry points to the same `AppConfig` object model. Pick whichever fits your workflow.
- Dynamic agent generation (one per tenant, one per dataset) is the primary reason to go programmatic.
- Mixing approaches is safe: load from YAML, then override fields in Python before calling `as_graph()`.

## Back to the workshop

[Chapter index](../README.md#chapter-index) | [Appendix: Advanced Topics](../appendix/)
