# Databricks notebook source
# MAGIC %md
# MAGIC # Sidebar - Programmatic Construction
# MAGIC
# MAGIC YAML is the default, but the same object model is exposed in
# MAGIC Python. Useful for generating agents dynamically.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 - Install dependencies

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.57"
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 - Build an agent in pure Python

# COMMAND ----------

from dao_ai.config import (
    AgentModel,
    AppConfig,
    AppModel,
    DeploymentTarget,
    LLMModel,
    OrchestrationModel,
    ResourcesModel,
    SwarmModel,
)

llm = LLMModel(name="databricks-claude-sonnet-4", temperature=0.1, max_tokens=2048)

greeter = AgentModel(
    name="greeter",
    description="Minimal agent built in code.",
    model=llm,
    prompt="You are the programmatic workshop assistant. Be brief.",
)

config = AppConfig(
    resources=ResourcesModel(llms={"default_llm": llm}),
    agents={"greeter": greeter},
    app=AppModel(
        name="dao_ws_98_programmatic",
        agents=[greeter],
        deployment_target=DeploymentTarget.APPS,
        orchestration=OrchestrationModel(swarm=SwarmModel(default_agent=greeter)),
    ),
)

agent = config.as_graph()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 - Invoke

# COMMAND ----------

response = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "Did this work?"}]},
)
print(response["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 - Deploy as a Databricks App
# MAGIC
# MAGIC `write_bundle()` works directly on the `AppConfig` instance --
# MAGIC no `dao_ai.yaml` file required.

# COMMAND ----------

from pathlib import Path

from dao_ai.apps.bundle import write_bundle

write_bundle(config, Path("."), force=True)
print("databricks.yaml generated from AppConfig")

# COMMAND ----------

# MAGIC %sh
# MAGIC set -euo pipefail
# MAGIC databricks bundle deploy -t dev
# MAGIC databricks bundle run dao-ws-98-programmatic -t dev

# COMMAND ----------

# MAGIC %md
# MAGIC ## When to use this vs. YAML
# MAGIC
# MAGIC - **YAML wins**: production agents, team review, config-as-code.
# MAGIC - **Python wins**: dynamic generation, tests, embedding dao-ai
# MAGIC   in a larger application.
