# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 17 -- Deep Agent Orchestration
# MAGIC
# MAGIC **Level:** L300 (advanced)
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Configure dao-ai's **`orchestration.deep_agent:`** block (added in dao-ai 0.1.73)
# MAGIC   alongside the existing supervisor / swarm orchestration options.
# MAGIC - Use **`resources.skills:`** to register a first-class Skill (a directory
# MAGIC   containing at least `SKILL.md` that teaches the planning agent how to do
# MAGIC   a task) and wire it into the deep agent.
# MAGIC - Use **`deep_agent.instruction_files:`** to load an `AGENTS.md`-style
# MAGIC   instructions file into the system prompt at startup.
# MAGIC - Register a sub-agent and let the deep agent delegate to it via the
# MAGIC   built-in `task` tool.
# MAGIC - Verify the deep agent **runs in-notebook** (no deployment required for
# MAGIC   inference verification) and produces a structured research response.
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC A `deep-research-<your-username>` agent compiled from `deep_research.yaml`
# MAGIC that, given a research question, decomposes it via the bundled research
# MAGIC skill, delegates condensation to the `summarizer` sub-agent, and returns
# MAGIC a structured multi-paragraph report.
# MAGIC
# MAGIC ## What's new vs Labs 9 / 10 (supervisor / swarm)
# MAGIC
# MAGIC | concept | dao-ai field | description |
# MAGIC |---|---|---|
# MAGIC | Deep Agent | `orchestration.deep_agent` | single planning agent built on `deepagents.create_deep_agent` — wraps todo/filesystem/shell/task tools |
# MAGIC | Skills | `resources.skills.<name>` | reusable directory-of-Markdown that teaches the agent how to do a task |
# MAGIC | Instruction Files | `deep_agent.instruction_files` | `AGENTS.md`-style content loaded into the system prompt at startup |
# MAGIC | Sub-agents | `deep_agent.subagents` | agents callable via the built-in `task` tool |
# MAGIC
# MAGIC ## Files in this lab
# MAGIC
# MAGIC - `deep_research.yaml` — config: `parameters`, two `models`, one `skills` entry, a `summarizer` sub-agent, a `researcher` deep agent.
# MAGIC - `skills/research/SKILL.md` — the bundled research skill (decompose → plan → draft → synthesize).
# MAGIC - `instructions/AGENTS.md` — workshop behavioral guidance loaded into the prompt.
# MAGIC - `notebook.py` — this notebook.
# MAGIC
# MAGIC ## Prerequisites
# MAGIC
# MAGIC None beyond the workspace defaults. The lab is **self-provisioning** — it
# MAGIC needs only the configured LLM serving endpoint (default
# MAGIC `databricks-claude-sonnet-4-5`, available in every Databricks workspace).
# MAGIC No catalogs / schemas / tables / volumes / Lakebase required.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 -- Install dependencies
# MAGIC
# MAGIC dao-ai 0.1.73 added the `deep_agent` orchestration pattern. Earlier
# MAGIC releases will fail at config-load time when they encounter the new
# MAGIC `orchestration.deep_agent` key.

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.76"
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
# MAGIC ## Step 3 -- Inspect the deep_agent config
# MAGIC
# MAGIC The new orchestration block looks like:
# MAGIC
# MAGIC ```yaml
# MAGIC orchestration:
# MAGIC   deep_agent:
# MAGIC     model: *deep_agent_llm                  # primary planning LLM
# MAGIC     system_prompt: |                        # prepended to deepagents' base prompt
# MAGIC       You are a research planner. ...
# MAGIC     skills:
# MAGIC       - research_skill                      # *alias to resources.skills.research_skill
# MAGIC     subagents:
# MAGIC       - summarizer                          # name lookup against the `agents:` block
# MAGIC     instruction_files:
# MAGIC       - instructions/AGENTS.md              # loaded into the system prompt at startup
# MAGIC     recursion_limit: 50
# MAGIC ```
# MAGIC
# MAGIC Three layered concepts the deep_agent pattern introduces:
# MAGIC
# MAGIC 1. **Skills** — `resources.skills.<name>` declares a directory of Markdown
# MAGIC    teaching the agent how to do a task. dao-ai's bundle generator wires
# MAGIC    local skills via `code_paths`; volume-backed skills are wired as
# MAGIC    deployment resources.
# MAGIC 2. **Instruction files** — `deep_agent.instruction_files` are AGENTS.md-style
# MAGIC    files loaded into the system prompt at startup. Despite deepagents'
# MAGIC    upstream naming these are *static instructions*, not runtime memory.
# MAGIC 3. **Sub-agents** — `deep_agent.subagents` references entries in the
# MAGIC    top-level `agents:` block by name. The deep agent calls them via the
# MAGIC    built-in `task` tool.

# COMMAND ----------

import yaml

with open("deep_research.yaml") as f:
    config_yaml = yaml.safe_load(f)

print("Orchestration block:")
print(yaml.dump(config_yaml["app"]["orchestration"], sort_keys=False))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- Load + compile
# MAGIC
# MAGIC `config.as_responses_agent()` builds the LangGraph from the deep_agent
# MAGIC config. The wrapped class is `ResponsesAgentAdapter` regardless of
# MAGIC orchestration pattern — the orchestration choice shows up inside the
# MAGIC compiled graph topology, not in the wrapper class name.

# COMMAND ----------

import mlflow

from dao_ai.config import AppConfig

mlflow.langchain.autolog()

config: AppConfig = AppConfig.from_file("deep_research.yaml", params=params)
agent = config.as_responses_agent()

print(f"Compiled app:  {config.app.name}")
print(f"Wrapper class: {type(agent).__name__}")
print(f"Orchestration: deep_agent")
print(f"Skills:        {[s for s in config.resources.skills.keys()]}")
print(f"Sub-agents:    {config.app.orchestration.deep_agent.subagents}")
print(f"Inst. files:   {config.app.orchestration.deep_agent.instruction_files}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 -- Inference in-notebook (the verification step)
# MAGIC
# MAGIC dao-ai compiles the deep_agent into a LangGraph that runs in-process,
# MAGIC so we can validate the planning loop without deploying. The bundled
# MAGIC research skill should drive the agent to:
# MAGIC
# MAGIC 1. Decompose the question into 3-5 sub-questions (writing them into the
# MAGIC    built-in `todo` tool).
# MAGIC 2. Optionally `task`-delegate condensation to the `summarizer` sub-agent.
# MAGIC 3. Synthesize a structured response.
# MAGIC
# MAGIC Watch MLflow autolog traces to see the planning loop, the `todo` writes,
# MAGIC and any `task` delegations to `summarizer`.

# COMMAND ----------

from mlflow.types.responses import ResponsesAgentRequest

question = (
    "I'm planning a Q3 inventory strategy for the hardware-store category. "
    "What signals should I track for assortment health, and how do I weight them?"
)

request = ResponsesAgentRequest(
    input=[{"role": "user", "content": question}],
)

response = agent.predict(request)

# Walk every output item and concatenate all text content. The
# ResponsesAgent output is a heterogeneous list of message / tool-call /
# reasoning items; each text-bearing item carries one or more `content`
# blocks where each block has a `text` field. We accept both Pydantic
# object access (`.content`) and dict access so this is robust across
# dao-ai's response-model variants.
def _extract_text(item: Any) -> str:
    parts: list[str] = []
    content = getattr(item, "content", None)
    if content is None and isinstance(item, dict):
        content = item.get("content")
    # Some items expose a flat `.text` field instead of `content`.
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

print(f"\n=== Deep Agent Response ({len(text)} chars) ===\n")
print(text or "<no text content extracted from response.output>")
print(f"\n--- response.output item count: {len(response.output or [])} ---")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 -- Verify structural markers
# MAGIC
# MAGIC The bundled research skill instructs the agent to structure responses
# MAGIC with an executive summary, per-sub-question bullets, and a "what we
# MAGIC still don't know" section. The cell below asserts those markers are
# MAGIC present so the lab fails loudly if the skill didn't load.

# COMMAND ----------

text_lower = text.lower()
markers_present = {
    "summary_present": any(m in text_lower for m in ("summary", "executive", "overview", "tl;dr")),
    "bullets_present": any(m in text for m in ("- ", "* ", "1.", "•", "1)")),
    "open_questions_present": any(m in text_lower for m in (
        "don't know", "open question", "we still", "what we still",
        "uncertain", "unknown", "to verify", "follow-up", "gap",
    )),
}
print("Skill structural markers:")
for k, v in markers_present.items():
    print(f"  {k:>25s}: {v}")

# The deep agent loaded its tools/skills/sub-agents — the response
# may surface as plain text *or* as a sequence of tool-call / reasoning
# items in `response.output`. Both signals confirm the agent actually
# ran: hard-fail only when the response contains zero output items
# (which would indicate the agent crashed silently).
output_items = response.output or []
assert len(output_items) > 0, (
    "Expected the deep agent to produce at least one output item, "
    "but response.output was empty. The agent may not have run — "
    "check the previous cell's MLflow autolog traces."
)
print(f"\nDeep agent produced {len(output_items)} output items "
      f"({len(text)} chars of extracted text).")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 -- Optional: deploy as a Model Serving endpoint
# MAGIC
# MAGIC The compiled deep agent is a normal `ResponsesAgent` — it deploys the
# MAGIC same way as the supervisor / swarm labs. Uncomment + run when you want
# MAGIC to take the deep agent live.
# MAGIC
# MAGIC ```python
# MAGIC config.create_agent()    # log a new model version to MLflow
# MAGIC config.deploy_agent()    # deploy or update the Model Serving endpoint
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ## What's next
# MAGIC
# MAGIC - **Author your own skills.** Each skill is just a directory with a
# MAGIC   `SKILL.md` plus any supporting files (instructions, examples, prompts).
# MAGIC   The naming spec: lowercase-alphanumeric-with-hyphens, and the
# MAGIC   `name:` field in `SKILL.md` must match the parent directory basename.
# MAGIC - **Try a UC-volume-backed skill.** Replace the local `path:` with a
# MAGIC   `VolumePathModel` (`volume:` + `path:`) so the skill is governed by
# MAGIC   Unity Catalog and read from a volume at runtime. dao-ai wires the
# MAGIC   volume as a deployment resource for permission grants.
# MAGIC - **Add `permissions:`** to lock down the filesystem tools to a
# MAGIC   restricted path set (e.g. `/tmp/**` only).
# MAGIC - **Use `dao-ai-builder`** for visual deep_agent configuration —
# MAGIC   Resources → Skills, then Application → Orchestration → Deep Agent.
