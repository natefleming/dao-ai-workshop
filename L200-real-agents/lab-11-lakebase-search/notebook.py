# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 11 -- Lakebase Search Retrieval
# MAGIC
# MAGIC **Level:** L200
# MAGIC
# MAGIC Build a knowledge-base assistant that retrieves from **Lakebase Postgres**
# MAGIC using hybrid dense + BM25 search with FlashRank reranking. Same tool
# MAGIC schema as `ai_search`; different backend.

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.106"
# MAGIC %restart_python

# COMMAND ----------

import re
from databricks.sdk import WorkspaceClient

w: WorkspaceClient = WorkspaceClient()
short_name: str = w.current_user.me().user_name.split("@")[0].lower()
username: str = re.sub(r"[^a-z0-9]+", "-", short_name).strip("-")[:13]

dbutils.widgets.text("lakebase_project", "retail-consumer-goods", "Lakebase project")
dbutils.widgets.text("sp_secret_scope", "dao_ai_workshop", "SP secret scope")

params: dict[str, str] = {
    "username": username,
    "lakebase_project": dbutils.widgets.get("lakebase_project").strip(),
    "sp_secret_scope": dbutils.widgets.get("sp_secret_scope").strip(),
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load the config

# COMMAND ----------

from dao_ai.config import (
    AppConfig,
    DatabaseModel,
    LakebaseRetrieverModel,
    LakebaseVectorStoreModel,
)

config: AppConfig = AppConfig.from_file("kb_assistant.yaml", params=params)
retriever: LakebaseRetrieverModel = config.retrievers["kb_retriever"]
vector_store: LakebaseVectorStoreModel = retriever.vector_store
database: DatabaseModel = vector_store.database

# COMMAND ----------

# MAGIC %md
# MAGIC ## Provision the Lakebase table
# MAGIC
# MAGIC `provision()` idempotently creates the extensions (`lakebase_vector`,
# MAGIC `lakebase_text`), the `kb_articles` table, and the ANN + BM25 indexes.
# MAGIC Safe to re-run.

# COMMAND ----------

vector_store.provision(
    dimension=1024,  # databricks-gte-large-en output dimension
    metadata_column_types={"priority": "int"},
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Seed the KB rows

# COMMAND ----------

from pathlib import Path

seed_sql: str = Path("data/kb_articles.seed.sql").read_text()
database.execute_sql(seed_sql)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Backfill embeddings
# MAGIC
# MAGIC The seed rows have `embedding=NULL` so the DDL stays portable across
# MAGIC embedding models. Encode each passage now.

# COMMAND ----------

from databricks_langchain import DatabricksEmbeddings
from dao_ai.memory.postgres import PostgresPoolManager

embedder: DatabricksEmbeddings = DatabricksEmbeddings(endpoint="databricks-gte-large-en")
pool = PostgresPoolManager.get_pool(database)

with pool.connection() as conn, conn.cursor() as cur:
    cur.execute("SELECT id, passage FROM kb_articles WHERE embedding IS NULL")
    rows: list[dict] = cur.fetchall()
    if rows:
        vectors: list[list[float]] = embedder.embed_documents([r["passage"] for r in rows])
        for row, vec in zip(rows, vectors):
            cur.execute(
                "UPDATE kb_articles SET embedding = %s::vector WHERE id = %s",
                (vec, row["id"]),
            )
        conn.commit()
    print(f"backfilled {len(rows)} embeddings")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Retrieve

# COMMAND ----------

import json

tool = config.tools["kb_search"].function.as_tools()[0]
docs: list[dict] = json.loads(tool.invoke({"query": "How do I reset my password?"}))
for doc in docs:
    meta: dict = doc["metadata"]
    print(f"[{meta['id']}] priority={meta['priority']} :: {doc['page_content']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cleanup (optional)

# COMMAND ----------

# database.execute_sql("DROP TABLE IF EXISTS kb_articles;")
