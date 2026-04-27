# L100 Debrief

> Reflection · L100 Foundations

You've finished L100. Take a few minutes to consolidate what you've learned before moving to L200.

## Reflect

- **What surprised you?** Most students are surprised that a deployable agent is ~30 lines of YAML rather than a few hundred lines of Python.
- **What felt familiar?** The resource registry / declarative config pattern is similar to Asset Bundles, Terraform, Helm, Kubernetes manifests. If you've used any of those, the DAO-AI shape should feel natural.
- **What still feels shaky?** A common one: when to use `&anchor` / `*alias` vs. just inlining a value. Rule of thumb: alias when the same value is referenced from 2+ places (LLM resources, schemas, databases). Inline when it's used once.

## Common gotchas you might have hit

| Gotcha | Symptom | Fix |
|---|---|---|
| Forgetting to pass a required `parameter` | `ConfigVariableError: required parameter not set` | Add it to the `params={...}` dict in the notebook, or give the parameter a `default:` |
| Wrong YAML indentation | `yaml.YAMLError` or unexpected `null` values | YAML is whitespace-sensitive. Use 2 spaces consistently. |
| `${var.NAME}` not substituted | Config loads but a literal `${var.NAME}` string ends up in the agent's deployed name | The parameter must be both *declared* in `parameters:` and *referenced* with `${var.NAME}` -- check both. |
| App name collisions across students | `databricks bundle deploy` complains the app already exists | The `${var.username}` parameter is the fix -- make sure your notebook is deriving and passing it. |
| MCP discovery returns no tools (Lab 4) | "I don't have a tool for that" | Lab 2's UC functions must exist in `<your_catalog>.dao_ai.*`. Re-run Lab 2 if you skipped it. |

## What's next: L200

L100 covered the DAO-AI surface for **building a tool-using agent**. L200 covers the patterns that separate a demo from production:

- External integrations beyond UC (REST tools).
- Retrieval over your own knowledge base (vector search + reranking).
- Memory across turns and sessions (Lakebase-backed).
- Quality controls (managed prompts + judge guardrails).
- Multi-agent coordination (supervisor, swarm).

The use case also switches: L200 moves from a customer-facing hardware-store assistant to an internal SaaS support agent. The DAO-AI patterns are identical -- the domain framing changes so that each L200 lab's config can stay tightly scoped to its new feature.

[**On to L200 → Building Real Agents**](../L200-real-agents/)
