-- Lab 11 -- Lakebase KB articles DDL + seed data
-- ---------------------------------------------------------------
-- Run this in the Databricks SQL editor against your Lakebase project's
-- Postgres database. The notebook expects the schema + table to exist
-- and backfills the `embedding` column with vectors from the configured
-- embedding endpoint (databricks-gte-large-en, dimension 1024).
--
-- Prerequisites:
--   * A Lakebase project provisioned in the workspace
--   * A Postgres database inside the project (default: databricks_postgres)
--   * The `lakebase_vector` extension is available on Lakebase autoscaling
--     endpoints; `lakebase_text` provides BM25 support on tsvector columns.
--   * Your Lakebase database role has CREATE privileges on `public`.

-- 1) Extensions --------------------------------------------------
CREATE EXTENSION IF NOT EXISTS lakebase_vector CASCADE;
CREATE EXTENSION IF NOT EXISTS lakebase_text;

-- 2) Table -------------------------------------------------------
--   * `embedding` is left NULL at INSERT time -- the notebook's
--     embedding-backfill cell populates it after the table is seeded,
--     so the DDL is portable across embedding-model dimensions.
--   * `passage_tsv` is computed inline via `to_tsvector('english', ...)`
--     so BM25 works immediately without a separate backfill step.
DROP TABLE IF EXISTS kb_articles;
CREATE TABLE kb_articles (
    id           text PRIMARY KEY,
    category     text NOT NULL,
    priority     int  NOT NULL,
    passage      text NOT NULL,
    embedding    vector(1024),
    passage_tsv  tsvector GENERATED ALWAYS AS (to_tsvector('english', passage)) STORED
);

-- 3) Indexes -----------------------------------------------------
--   * `lakebase_ann` powers ANN search over the embedding column.
--   * `lakebase_bm25` powers BM25 / HYBRID over the tsvector column.
CREATE INDEX kb_articles_embedding_ann
    ON kb_articles USING lakebase_ann (embedding vector_cosine_ops);

CREATE INDEX kb_articles_passage_bm25
    ON kb_articles USING lakebase_bm25 (passage_tsv);

-- 4) Seed data ---------------------------------------------------
--   Ten articles across three categories (auth, billing, shipping).
--   `priority` is an integer tier: 1 = highest, 5 = lowest.
INSERT INTO kb_articles (id, category, priority, passage) VALUES
    ('d01', 'auth',     1, 'To reset your password, go to Settings > Security > Reset password. A reset email arrives within 5 minutes.'),
    ('d02', 'auth',     2, 'Enable multi-factor authentication (MFA) from your account security page. Supported: TOTP, SMS, WebAuthn.'),
    ('d03', 'auth',     3, 'If you forgot your username, contact support with the email address on file for account recovery.'),
    ('d04', 'auth',     1, 'Password reset links expire after 24 hours for security reasons. Request a new one from the login page.'),
    ('d05', 'billing',  1, 'Refunds for annual subscriptions are prorated based on unused months. Refunds process in 5-10 business days.'),
    ('d06', 'billing',  2, 'To update your payment method, go to Account > Billing > Payment methods and add a new card or bank account.'),
    ('d07', 'billing',  3, 'Invoices are generated on the 1st of each month and emailed to the account owner. Historical invoices are in Billing > History.'),
    ('d08', 'shipping', 1, 'Standard shipping takes 3-5 business days. Expedited shipping (extra fee) is 1-2 business days.'),
    ('d09', 'shipping', 2, 'International shipping is available to 40+ countries; customs fees are the recipients responsibility.'),
    ('d10', 'shipping', 3, 'To track a shipment, open the order in Account > Orders and click the tracking number below the shipping address.');
