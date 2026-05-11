# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 18 -- Skills-only Deep Agent
# MAGIC
# MAGIC **Level:** L300 (advanced)
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Configure a dao-ai deep_agent with **zero top-level agents and zero
# MAGIC   sub-agents** — only a Skill + system prompt.
# MAGIC - Verify dao-ai's `app.agents: []` carve-out under the deep_agent
# MAGIC   orchestration pattern (validator at `config.py:6531-6540`).
# MAGIC - Run in-notebook inference against the compiled deep agent and
# MAGIC   confirm the planning agent uses the bundled `code_review` skill.
# MAGIC
# MAGIC ## Why a skills-only deep agent?
# MAGIC
# MAGIC Lab 17 introduced the deep_agent pattern with a researcher + summarizer
# MAGIC sub-agent. That works, but when your specialist agent doesn't need to
# MAGIC delegate to a *different* model or persona, you don't need a sub-agent
# MAGIC at all. The planner can do all the work with its built-in
# MAGIC `todo` / `filesystem` / `shell` / `task` tools plus the Skill.
# MAGIC
# MAGIC Choose **skills-only** when:
# MAGIC
# MAGIC - You're building a single specialist (code reviewer, bug triager,
# MAGIC   release-notes author, API critic, …).
# MAGIC - You want to govern *methodology* via Skills (versioned Markdown
# MAGIC   directories) rather than embed it in a long inline prompt string.
# MAGIC - You don't need delegation to a different model / persona.
# MAGIC
# MAGIC ## What this lab confirms (the new dao-ai 0.1.73+ behavior)
# MAGIC
# MAGIC dao-ai's `AppModel.validate_agents_not_empty` model_validator allows
# MAGIC `app.agents: []` **only when** `orchestration.deep_agent` is set:
# MAGIC
# MAGIC ```python
# MAGIC @model_validator(mode="after")
# MAGIC def validate_agents_not_empty(self) -> Self:
# MAGIC     if self.orchestration is not None and self.orchestration.deep_agent is not None:
# MAGIC         return self
# MAGIC     raise ValueError("At least one agent must be specified")
# MAGIC ```
# MAGIC
# MAGIC Supervisor / swarm / no-orchestration still require at least one agent.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 -- Install dependencies

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.73"
# MAGIC %restart_python

# COMMAND ----------

from importlib.metadata import version

print(f"dao-ai={version('dao-ai')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 -- Configure parameters

# COMMAND ----------

import re
from typing import Any

from databricks.sdk import WorkspaceClient

w: WorkspaceClient = WorkspaceClient()
short_name: str = w.current_user.me().user_name.split("@")[0].lower()
username: str = re.sub(r"[^a-z0-9]+", "-", short_name).strip("-")[:13]
print(f"Derived username: {username}")

dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-4-5", "LLM endpoint")

params: dict[str, str] = {
    "username": username,
    "llm_endpoint": dbutils.widgets.get("llm_endpoint").strip(),
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 -- Inspect the config shape
# MAGIC
# MAGIC Two things to notice in `code_reviewer.yaml`:
# MAGIC
# MAGIC 1. **`app.agents: []`** — explicitly empty. No `researcher`, no
# MAGIC    `summarizer`, no top-level agent definitions anywhere.
# MAGIC 2. **`orchestration.deep_agent`** — carries the model, system prompt,
# MAGIC    one skill (`code_review_skill`), one instruction file. No
# MAGIC    `subagents:` block.
# MAGIC
# MAGIC This is the minimum viable deep agent: one planner + one skill.

# COMMAND ----------

import yaml

with open("code_reviewer.yaml") as f:
    config_yaml = yaml.safe_load(f)

print(f"Top-level agents in resources: {list(config_yaml.get('resources', {}).get('llms', {}).keys())}")
print(f"app.agents:                    {config_yaml['app'].get('agents', '<not set>')}")
print(f"orchestration.deep_agent keys: {list(config_yaml['app']['orchestration']['deep_agent'].keys())}")
print(f"  -> subagents present?        {'subagents' in config_yaml['app']['orchestration']['deep_agent']}")
print(f"  -> skills:                   {config_yaml['app']['orchestration']['deep_agent']['skills']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- Load + compile
# MAGIC
# MAGIC `AppConfig.from_file(...)` parses the YAML. dao-ai's
# MAGIC `validate_agents_not_empty` validator runs here and accepts the
# MAGIC empty `app.agents` list because `orchestration.deep_agent` is
# MAGIC present. If you removed the `deep_agent:` block this cell would
# MAGIC raise a Pydantic `ValidationError`.

# COMMAND ----------

import mlflow

from dao_ai.config import AppConfig

mlflow.langchain.autolog()

config: AppConfig = AppConfig.from_file("code_reviewer.yaml", params=params)
agent = config.as_responses_agent()

print(f"Compiled app:        {config.app.name}")
print(f"Wrapper class:       {type(agent).__name__}")
print(f"app.agents length:   {len(config.app.agents)}")
print(f"Skills:              {list(config.resources.skills.keys())}")
print(f"Sub-agents declared: {config.app.orchestration.deep_agent.subagents}")
print(f"Instruction files:   {config.app.orchestration.deep_agent.instruction_files}")

assert len(config.app.agents) == 0, (
    "Lab 18 expects an empty app.agents list. If you see entries here, "
    "the YAML was edited or merged with Lab 17's config."
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 -- Inference in-notebook
# MAGIC
# MAGIC Submit a short code snippet for review. The planning agent should:
# MAGIC
# MAGIC 1. Open the bundled `code_review` skill (loaded by deepagents'
# MAGIC    `SkillsMiddleware`) to retrieve its review methodology.
# MAGIC 2. Use the built-in `todo` tool to enumerate review concerns
# MAGIC    (correctness, edge cases, error handling, naming, tests, …).
# MAGIC 3. Synthesize a structured review.
# MAGIC
# MAGIC No sub-agent delegation happens — there are no sub-agents to call.
# MAGIC The entire review is produced by the single planning agent.

# COMMAND ----------

from mlflow.types.responses import ResponsesAgentRequest

snippet = '''
def divide(a, b):
    """Divide a by b and return the result."""
    result = a / b
    return result


def parse_user_id(text):
    # Extract a numeric user_id from a free-form string like "user 42 logged in"
    for word in text.split():
        if word.isdigit():
            return int(word)
'''.strip()

prompt = (
    "Review the following Python code from a Databricks notebook. "
    "It will be called from a long-running daily job that processes "
    "millions of records.\n\n"
    "```python\n" + snippet + "\n```"
)

request = ResponsesAgentRequest(input=[{"role": "user", "content": prompt}])
response = agent.predict(request)

# Robust text extraction — mirror lab-17's helper. The ResponsesAgent
# output is a heterogeneous list of message / tool-call / reasoning
# items; walk every item and pull every text-bearing block.
def _extract_text(item: Any) -> str:
    parts: list[str] = []
    content = getattr(item, "content", None)
    if content is None and isinstance(item, dict):
        content = item.get("content")
    flat = getattr(item, "text", None) or (item.get("text") if isinstance(item, dict) else None)
    if isinstance(flat, str):
        parts.append(flat)
    if isinstance(content, list):
        for block in content:
            t = getattr(block, "text", None)
            if t is None and isinstance(block, dict):
                t = block.get("text")
            if isinstance(t, str):
                parts.append(t)
    return "\n".join(p for p in parts if p)

text = "\n\n".join(_extract_text(item) for item in (response.output or []) if _extract_text(item))

print(f"\n=== Code Review Response ({len(text)} chars) ===\n")
print(text or "<no text content extracted from response.output>")
print(f"\n--- response.output item count: {len(response.output or [])} ---")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 -- Confirm the agent actually ran
# MAGIC
# MAGIC The deep agent's response may surface as plain text *or* as a
# MAGIC sequence of tool-call / reasoning items in `response.output`. Both
# MAGIC signals confirm the agent ran. Hard-fail only when the response
# MAGIC contains zero output items.

# COMMAND ----------

output_items = response.output or []
assert len(output_items) > 0, (
    "Expected the deep agent to produce at least one output item, "
    "but response.output was empty. The agent may not have run — "
    "check the previous cell's MLflow autolog traces."
)
print(f"Deep agent produced {len(output_items)} output items "
      f"({len(text)} chars of extracted text).")

# Smoke-check that the response is shaped like a review. Soft signals
# rather than hard asserts so the lab doesn't fail on natural-language
# variation between LLM responses.
text_lower = text.lower()
soft_signals = {
    "verdict_present": any(m in text_lower for m in ("approve", "request changes", "needs work", "lgtm")),
    "concern_categories": sum(
        1 for kw in ("correctness", "edge case", "error", "naming", "test", "performance", "security")
        if kw in text_lower
    ),
    "quotes_offending_code": any(m in text for m in ("divide", "parse_user_id", "a / b", "isdigit")),
}
print("Review structural signals:")
for k, v in soft_signals.items():
    print(f"  {k:>22s}: {v}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 -- (Optional) Try the negative case
# MAGIC
# MAGIC Uncomment + run this cell to see what happens when you remove the
# MAGIC `orchestration.deep_agent` block from the config while keeping
# MAGIC `app.agents: []`. dao-ai's validator should reject the config with
# MAGIC `At least one agent must be specified`.
# MAGIC
# MAGIC ```python
# MAGIC from dao_ai.config import AppConfig, AppModel, OrchestrationModel
# MAGIC try:
# MAGIC     bad_config = AppConfig(
# MAGIC         app=AppModel(name="negative-test", deployment_target="apps", agents=[]),
# MAGIC     )
# MAGIC except Exception as e:
# MAGIC     print(f"Correctly rejected: {type(e).__name__}: {e}")
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ## What's next
# MAGIC
# MAGIC - **Lab 17** for the deep_agent pattern with a sub-agent.
# MAGIC - **Lab 18 (this lab)** for the skills-only deep_agent pattern.
# MAGIC - Compose multiple skills inside one deep_agent — add a second
# MAGIC   directory under `skills/` and reference it under
# MAGIC   `deep_agent.skills` in the YAML.
# MAGIC - Promote a local skill to a UC-volume-backed skill by replacing
# MAGIC   the `path:` string with a `VolumePathModel` (`volume:` + `path:`).
