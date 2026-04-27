# Setting the Stage

> Lecture · L100 Foundations · 10 min read

## What is an agent?

An LLM by itself returns **text**. It doesn't read your databases, it doesn't call your APIs, it doesn't remember anything beyond the current message. For most production work that's not enough.

An **agent** wraps an LLM with a loop:

1. **The model picks an action.** Given the user's message and a list of tools it could call, the model decides whether to call one and which arguments to pass.
2. **The framework runs the action.** A function executes -- a SQL query, an HTTP call, a vector lookup, whatever the tool does.
3. **The result feeds back to the model.** The tool's output becomes part of the next prompt.
4. **Repeat until the model answers.**

That's it. Multi-agent systems just add the wrinkle that *which agent answers* can also be a decision the framework makes -- but the inner loop is the same.

## Why DAO-AI

You can build that loop in Python by hand. You write a `StateGraph`, define nodes, add conditional edges, register tools, manage message history. It works, but you end up reading framework internals to debug your own agent.

DAO-AI inverts the model. **You don't write the agent in Python -- you describe it in YAML.** The framework reads the YAML and generates the loop.

A single-tool agent in DAO-AI is roughly this:

```yaml
parameters:
  llm_endpoint:
    default: databricks-claude-sonnet-4-5

resources:
  llms:
    default_llm: &default_llm
      name: ${var.llm_endpoint}

agents:
  greeter:
    name: greeter
    model: *default_llm
    prompt: |
      You are a friendly assistant. Greet the user warmly.

app:
  name: greeter-${var.username}
  agents: [*greeter]
  orchestration:
    swarm:
      default_agent: *greeter
```

That's a complete, deployable agent. You'll write something very close to this in Lab 1.

## What DAO-AI does not hide

DAO-AI does abstract LangGraph internals -- the `StateGraph`, the `MessagesState`, the conditional routing logic. Those are the framework's job. **You will not learn LangGraph in this workshop.** That's deliberate.

What you *will* learn is what to put in the YAML to get the agent shape you want. The whole workshop is teaching one skill: composing DAO-AI configs.

## Single-agent vs. multi-agent

Most of the labs build a single agent with one or more tools. **Lab 9 (Multi-agent Orchestration)** introduces multiple agents coordinated by a supervisor or a swarm. The same DAO-AI concepts apply -- you just declare more agents and add an `orchestration` block to the `app`.

## What's next

[**Anatomy of a DAO-AI Config**](anatomy-of-a-config.md) walks through the four YAML sections every DAO-AI config has, with a minimal end-to-end example.
