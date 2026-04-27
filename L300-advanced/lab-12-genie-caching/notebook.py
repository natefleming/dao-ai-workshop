# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 12 -- Genie Context-Aware Caching
# MAGIC
# MAGIC **Level:** L300 (advanced)
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Wrap a Genie Space with **two** layers of caching: an L1 LRU exact-match cache and an L2 context-aware similarity cache.
# MAGIC - Watch L1 hit on identical repeat questions (sub-millisecond).
# MAGIC - Watch L2 hit on near-duplicate questions (similarity-based).
# MAGIC - Understand why the cache stores the **SQL** (not the answer) and re-executes it on each hit.
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC A `cached-analyst-<your-username>` agent where the same analytical question runs in `O(seconds)` on the first call and `O(milliseconds)` on the second/third (L1 hit), and a re-phrasing of the question is also served from cache (L2 hit).

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 -- Install dependencies

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.63"
# MAGIC %restart_python

# COMMAND ----------

from importlib.metadata import version

print(f"dao-ai={version('dao-ai')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 -- Configure parameters

# COMMAND ----------

import re

from databricks.sdk import WorkspaceClient
from langgraph.graph.state import CompiledStateGraph
from typing import Any

w: WorkspaceClient = WorkspaceClient()
short_name: str = w.current_user.me().user_name.split("@")[0].lower()
username: str = re.sub(r"[^a-z0-9]+", "-", short_name).strip("-")[:13]
print(f"Derived username: {username}")

dbutils.widgets.text("genie_space_id", "", "Genie Space ID (over the products table)")
dbutils.widgets.text("warehouse_id", "", "SQL warehouse ID (for cache replay)")
dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-4-5", "LLM endpoint")
dbutils.widgets.text("embedding_model", "databricks-gte-large-en", "Embedding endpoint")

genie_space_id: str = dbutils.widgets.get("genie_space_id").strip()
warehouse_id: str = dbutils.widgets.get("warehouse_id").strip()
if not genie_space_id or not warehouse_id:
    raise ValueError("Set both genie_space_id and warehouse_id widgets.")

params: dict[str, str] = {
    "username": username,
    "genie_space_id": genie_space_id,
    "warehouse_id": warehouse_id,
    "llm_endpoint": dbutils.widgets.get("llm_endpoint").strip(),
    "embedding_model": dbutils.widgets.get("embedding_model").strip(),
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 -- Two cache layers in one tool block
# MAGIC
# MAGIC The interesting bit in `cached_analyst.yaml` is the
# MAGIC `args:` block of the Genie tool factory:
# MAGIC
# MAGIC ```yaml
# MAGIC tools:
# MAGIC   cached_genie:
# MAGIC     function:
# MAGIC       type: factory
# MAGIC       name: dao_ai.tools.create_genie_toolkit
# MAGIC       args:
# MAGIC         genie_room: *products_genie
# MAGIC
# MAGIC         # ---- L1: LRU exact-match cache ----
# MAGIC         lru_cache_parameters:
# MAGIC           warehouse: *cache_warehouse
# MAGIC           capacity: 100
# MAGIC           time_to_live_seconds: 3600
# MAGIC
# MAGIC         # ---- L2: in-memory context-aware similarity cache ----
# MAGIC         in_memory_context_aware_cache_parameters:
# MAGIC           warehouse: *cache_warehouse
# MAGIC           embedding_model: *embedding_model
# MAGIC           similarity_threshold: 0.85
# MAGIC           context_similarity_threshold: 0.80
# MAGIC           context_window_size: 3
# MAGIC ```
# MAGIC
# MAGIC The factory is `create_genie_toolkit` (not `create_genie_tool`)
# MAGIC -- the toolkit factory is what enables the cache parameters.
# MAGIC
# MAGIC **Important:** the cache stores the generated **SQL**, not the
# MAGIC answer. On a cache hit the SQL is re-executed against the
# MAGIC warehouse so the data is always fresh -- only the
# MAGIC question→SQL step is reused.

# COMMAND ----------

from dao_ai.config import AppConfig

config: AppConfig = AppConfig.from_file("cached_analyst.yaml", params=params)
agent: CompiledStateGraph = config.as_graph()

print(f"Compiled app name: {config.app.name}")
try:
    config.display_graph()
except Exception as e:
    print(f"An exception has occurred: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- L1 (LRU exact-match) cache demonstration
# MAGIC
# MAGIC Run the same question three times. The first call goes through
# MAGIC Genie and populates the cache. The next two should hit L1 and
# MAGIC return in milliseconds.

# COMMAND ----------

import time

q = "How many products do we have per category?"

print(f"Question: {q!r}\n")
for i in range(3):
    start = time.time()
    resp = await agent.ainvoke({"messages": [{"role": "user", "content": q}]})
    elapsed = time.time() - start
    label = "MISS (Genie API call)" if i == 0 else "HIT (L1 LRU cache)"
    print(f"Run {i + 1}: {elapsed:.2f}s   -- {label}")

print()
print("Last response:")
print(resp["messages"][-1].content)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 -- L2 (context-aware similarity) cache demonstration
# MAGIC
# MAGIC Run a **re-phrasing** of the same question. L1 won't match
# MAGIC (different bytes). L2 should match because question similarity
# MAGIC exceeds 0.85 and the conversation context is empty (so context
# MAGIC similarity also passes).

# COMMAND ----------

rephrasings = [
    "Give me the count of products in each category.",
    "What's the breakdown of products by category?",
    "Per category, how many products do we have?",
]

for q in rephrasings:
    start = time.time()
    resp = await agent.ainvoke({"messages": [{"role": "user", "content": q}]})
    elapsed = time.time() - start
    print(f"{elapsed:.2f}s -- {q!r}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 -- Tuning notes
# MAGIC
# MAGIC | Knob | Effect |
# MAGIC |---|---|
# MAGIC | `l1_capacity` | LRU cache size (entries). Bigger = more hits, more memory. |
# MAGIC | `l1_ttl_seconds` | LRU entry expiry. Lower = fresher SQL, fewer hits. |
# MAGIC | `l2_similarity_threshold` | Question-similarity floor for L2 hits. **0.85** is the documented sweet spot; **0.95** is more conservative; **0.75** is more aggressive. |
# MAGIC | `l2_context_similarity_threshold` | Context-similarity floor. Same scale; defaults to 0.80. |
# MAGIC | `l2_context_window_size` | How many prior turns count as context. **3** is a typical default. |
# MAGIC
# MAGIC Tune by watching cache hit rates in production. The dao-ai docs
# MAGIC reference (`dao-ai/config/examples/04_genie/cache_threshold_optimization.yaml`)
# MAGIC has a recipe for measuring and adjusting.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 -- Deploy as a Databricks App

# COMMAND ----------

from dao_ai.config import DeploymentTarget

config.deploy_agent(target=DeploymentTarget.APPS)
print(f"Deployed app: {config.app.name}")
