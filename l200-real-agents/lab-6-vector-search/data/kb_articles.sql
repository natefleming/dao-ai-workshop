USE IDENTIFIER(:database);

CREATE TABLE IF NOT EXISTS kb_articles (
  article_id STRING NOT NULL,
  title STRING NOT NULL,
  topic STRING NOT NULL,
  body STRING,
  published_at TIMESTAMP
) USING DELTA
TBLPROPERTIES (delta.enableChangeDataFeed = true);

INSERT INTO kb_articles VALUES
  ('KB-001', 'Rotating API keys without downtime', 'auth',          'Step-by-step guide to generating a new API key, deploying it alongside the old one, and revoking the old key after verification. Includes example code for common SDKs.', TIMESTAMP'2026-01-12 10:00:00'),
  ('KB-002', 'Configuring SSO with Azure AD',     'auth',          'Walks through SAML and OIDC setup, including IdP-side claim mapping and our app-side metadata configuration. Common errors and their fixes.', TIMESTAMP'2026-02-03 09:00:00'),
  ('KB-003', 'Resolving 401 errors',              'auth',          'A diagnostic checklist for unauthorized errors: token expiry, IP allowlists, scope mismatches, and clock drift between client and server.', TIMESTAMP'2026-01-20 11:30:00'),
  ('KB-004', 'Reading your monthly invoice',      'billing',       'Explains each line item on the monthly invoice: API calls, data warehouse storage, model serving, support uplift. Where to find historical invoices.', TIMESTAMP'2026-01-05 08:00:00'),
  ('KB-005', 'Switching billing tiers',           'billing',       'Guidance on flat-fee, usage-based, and committed-spend tiers. When to switch, what proration to expect, and rollback policy.', TIMESTAMP'2026-03-15 14:00:00'),
  ('KB-006', 'Bulk-exporting conversation history','data-export', 'API endpoint and CLI command for exporting up to 12 months of conversations as JSON. Pagination, rate limits, and file-format options.', TIMESTAMP'2026-02-22 16:00:00'),
  ('KB-007', 'GDPR data deletion requests',       'compliance',    'Process for requesting and verifying deletion of personal data within the 30-day SLA. Response template and audit logging.', TIMESTAMP'2026-01-30 12:00:00'),
  ('KB-008', 'Slack integration: deduplicating notifications', 'integration', 'Two common causes of duplicated Slack alerts and how to fix each. Includes a debug mode for inspecting webhook payloads.', TIMESTAMP'2026-03-08 13:00:00'),
  ('KB-009', 'Webhook retry policies',            'integration',   'Default retry behavior, how to configure exponential backoff, and how to verify webhook signatures. Examples in Python and TypeScript.', TIMESTAMP'2026-02-14 11:00:00'),
  ('KB-010', 'Investigating slow dashboard loads', 'performance',  'Step-by-step diagnostics for slow dashboards: caching layers, query plans, vector-search latency, and warm-pool sizing.', TIMESTAMP'2026-04-01 10:30:00'),
  ('KB-011', 'Migrating from v3 to v4',           'migration',     'Pre-migration checklist, schema diff, dual-write window, and post-migration data integrity verification.', TIMESTAMP'2026-03-22 09:00:00'),
  ('KB-012', 'Pagination cursor format reference','api',           'Cursor encoding, expiry, and back-compat behavior. How to upgrade clients that hard-coded the old cursor format.', TIMESTAMP'2026-04-10 14:00:00');
