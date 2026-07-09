# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 11 -- Knowledge-base Retrieval with Lakebase Search
# MAGIC
# MAGIC **Level:** L200
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Configure `databases:` for a Lakebase project + a `type: lakebase_search` retriever over a Postgres KB articles table.
# MAGIC - Compare three retrieval configurations against the same query: ANN only -> HYBRID (adds BM25) -> HYBRID + FlashRank cross-encoder rerank.
# MAGIC - See how `lakebase_search` reaches feature parity with `ai_search` -- same tool schema, same `rerank:` field, same `filters` shape -- but keeps the data on your existing Lakebase Postgres.
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC A `kb_assistant` agent that answers `"How do I reset my password?"` and `"When do password reset links expire?"` by retrieving and citing the matching kb_articles rows -- backed by Lakebase, not AI Search.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 -- Install dependencies

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.105"
# MAGIC %restart_python

# COMMAND ----------

from importlib.metadata import version

print(f"dao-ai={version('dao-ai')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 -- Configure parameters
# MAGIC
# MAGIC The `secret_scope` widget must point at a scope in your workspace that holds:
# MAGIC
# MAGIC | Secret key | Value |
# MAGIC |---|---|
# MAGIC | `SP_CLIENT_ID` | OAuth client id for a service principal with Lakebase access |
# MAGIC | `SP_CLIENT_SECRET` | Matching client secret |
# MAGIC | `DATABRICKS_HOST` | `https://<workspace>.cloud.databricks.com` |
# MAGIC
# MAGIC The `lakebase_project` widget must name a Lakebase project provisioned in the workspace. Rename the widget defaults if your keys differ.

# COMMAND ----------

import re
from typing import Any

from databricks.sdk import WorkspaceClient

w: WorkspaceClient = WorkspaceClient()
short_name: str = w.current_user.me().user_name.split("@")[0].lower()
username: str = re.sub(r"[^a-z0-9]+", "-", short_name).strip("-")[:13]
print(f"Derived username: {username}")

dbutils.widgets.text("lakebase_project", "", "Lakebase project name")
dbutils.widgets.text("secret_scope", "", "Secret scope (holds SP creds)")
dbutils.widgets.text("schema_name", "public", "Postgres schema")
dbutils.widgets.text("table_name", "kb_articles", "Postgres table")
dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-4-5", "LLM endpoint")
dbutils.widgets.text("embedding_model", "databricks-gte-large-en", "Embedding endpoint")
dbutils.widgets.dropdown(
    "reranker_model",
    "ms-marco-MiniLM-L-12-v2",
    ["ms-marco-MiniLM-L-12-v2", "ms-marco-TinyBERT-L-2-v2", "rank-T5-flan"],
    "Reranker (FlashRank)",
)

lakebase_project: str = dbutils.widgets.get("lakebase_project").strip()
secret_scope: str = dbutils.widgets.get("secret_scope").strip()
if not lakebase_project or not secret_scope:
    raise ValueError(
        "Set the `lakebase_project` and `secret_scope` widgets at the top of the notebook."
    )

params: dict[str, str] = {
    "username": username,
    "lakebase_project": lakebase_project,
    "secret_scope": secret_scope,
    "schema_name": dbutils.widgets.get("schema_name").strip(),
    "table_name": dbutils.widgets.get("table_name").strip(),
    "llm_endpoint": dbutils.widgets.get("llm_endpoint").strip(),
    "embedding_model": dbutils.widgets.get("embedding_model").strip(),
    "reranker_model": dbutils.widgets.get("reranker_model").strip(),
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 -- Provision the KB table (once per workspace)
# MAGIC
# MAGIC Open `data/kb_articles.sql` in the **Databricks SQL editor**, select your Lakebase project's database from the warehouse picker, and run the file. It creates:
# MAGIC
# MAGIC - The `lakebase_vector` and `lakebase_text` extensions
# MAGIC - The `kb_articles` table (with `passage_tsv` computed inline)
# MAGIC - `lakebase_ann` and `lakebase_bm25` indexes
# MAGIC - 10 seed rows across three categories (auth / billing / shipping)
# MAGIC
# MAGIC The `embedding` column is `NULL` after the DDL runs. The next cell backfills it by calling the configured embedding endpoint. Re-running the notebook is safe -- only rows with `NULL` embeddings get re-encoded.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Backfill embeddings
# MAGIC
# MAGIC Uses `AppConfig.from_file` to reach the same Lakebase connection the retriever will use -- `db.workspace_client_from(None)` mints an SDK client with the SP credentials from your secret scope.

# COMMAND ----------

from dao_ai.config import AppConfig
from databricks_langchain import DatabricksEmbeddings

CONFIG_PATH = "03_reranked.yaml"  # any of the 3 configs works -- same database block
_bootstrap_cfg = AppConfig.from_file(CONFIG_PATH, params=params)
_db = _bootstrap_cfg.resources.databases["kb_lakebase"]

embedder = DatabricksEmbeddings(endpoint=params["embedding_model"])

with _db.pool_sync().connection() as conn, conn.cursor() as cur:
    cur.execute(
        f'SELECT id, passage FROM {params["schema_name"]}.{params["table_name"]} '
        "WHERE embedding IS NULL"
    )
    rows = cur.fetchall()
    print(f"rows needing embeddings: {len(rows)}")
    if rows:
        ids = [r[0] for r in rows]
        vectors = embedder.embed_documents([r[1] for r in rows])
        for row_id, vec in zip(ids, vectors):
            cur.execute(
                f'UPDATE {params["schema_name"]}.{params["table_name"]} '
                "SET embedding = %s::vector WHERE id = %s",
                (vec, row_id),
            )
        conn.commit()
        print(f"backfilled {len(rows)} embeddings")
    else:
        print("nothing to backfill")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- Run the same query across three retrieval configurations
# MAGIC
# MAGIC Same question, three configs. Watch how the returned doc order shifts as we add BM25 (step 2) then FlashRank rerank (step 3).

# COMMAND ----------

import json
from typing import Any

QUERIES = [
    "How do I reset my password?",
    "When do password reset links expire?",
]


def call_kb_search(config_path: str, query: str) -> list[dict[str, Any]]:
    """Load a config, resolve its `kb_search` tool, and invoke it directly.

    Bypasses the agent LLM so we can inspect raw retrieval results.
    """
    cfg = AppConfig.from_file(config_path, params=params)
    tool_model = cfg.tools["kb_search"]
    tool = tool_model.as_tools()[0]  # StructuredTool
    raw = tool.invoke({"query": query})
    return json.loads(raw) if isinstance(raw, str) else raw


for config_path in ["01_ann_only.yaml", "02_hybrid.yaml", "03_reranked.yaml"]:
    print("\n" + "=" * 72)
    print(f"CONFIG: {config_path}")
    print("=" * 72)
    for q in QUERIES:
        print(f"\n  query: {q!r}")
        docs = call_kb_search(config_path, q)
        for i, doc in enumerate(docs, 1):
            meta = doc.get("metadata", {})
            print(
                f"    {i}. id={meta.get('id')!r} category={meta.get('category')!r} "
                f"priority={meta.get('priority')!r}"
            )
            print(f"       {doc.get('page_content', '')[:100]!r}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 -- Talk to the agent locally
# MAGIC
# MAGIC Use the final (reranked) config. The agent decides when to call `kb_search`, then answers with citations.

# COMMAND ----------

import nest_asyncio
import asyncio

nest_asyncio.apply()

from mlflow.types.responses import ResponsesAgentRequest

final_cfg = AppConfig.from_file("03_reranked.yaml", params=params)
final_cfg.initialize()
agent = final_cfg.as_responses_agent()

async def ask(question: str) -> str:
    resp = await agent.apredict(
        ResponsesAgentRequest(input=[{"role": "user", "content": question}])
    )
    for item in resp.output:
        if getattr(item, "type", None) == "message":
            for content in item.content:
                if content.get("type") in {"output_text", "text"}:
                    return content.get("text") or content.get("value") or ""
    return "<no text response>"

for q in QUERIES:
    print(f"\nQ: {q}")
    print(f"A: {asyncio.run(ask(q))}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 -- (Optional) Deploy as a Databricks App
# MAGIC
# MAGIC The final config is deployment-ready. To ship it:
# MAGIC
# MAGIC ```bash
# MAGIC dao-ai generate-bundle -c 03_reranked.yaml -o /tmp/kb_assistant_bundle \
# MAGIC   --param username=<yours> --param lakebase_project=<project> --param secret_scope=<scope>
# MAGIC cd /tmp/kb_assistant_bundle
# MAGIC databricks bundle deploy --target dev
# MAGIC dao-ai link-trace-destination -c ../03_reranked.yaml   # if you enable trace_location
# MAGIC databricks bundle run kb-assistant-<yours> --target dev
# MAGIC ```
# MAGIC
# MAGIC The deployed App SP needs `USE_SCHEMA` + `SELECT` on the Postgres schema. Grant via the Lakebase project's Data Access UI (Databricks does not surface Postgres-level grants through the workspace UC UI).
# MAGIC
# MAGIC ## Cleanup
# MAGIC
# MAGIC When you're done, drop the seed table from the SQL editor:
# MAGIC
# MAGIC ```sql
# MAGIC DROP TABLE IF EXISTS kb_articles;
# MAGIC ```
# MAGIC
# MAGIC ## Next
# MAGIC
# MAGIC - `notebook_programmatic.py` in this same lab -- the exact same agent, built from Python instead of YAML.
# MAGIC - [Lab 6](../lab-06-vector-search/) -- the `ai_search` sibling of this lab; same shape, Databricks Vector Search backend.
# MAGIC - [Lab 11 (L300)](../../L300-advanced/lab-11-instructed-retrieval/) -- adds LLM query decomposition + instruction-aware rerank on top of the same retriever.
