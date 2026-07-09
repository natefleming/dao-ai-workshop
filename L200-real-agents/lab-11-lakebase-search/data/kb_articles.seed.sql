-- Lab 11 -- Lakebase KB articles seed data
-- ---------------------------------------------------------------
-- 10 articles across three categories (auth, billing, shipping).
-- `priority` is an integer tier: 1 = highest, 5 = lowest.
--
-- Schema (extensions, table, indexes) is created idempotently by
-- `LakebaseVectorStoreModel.provision()` in the notebook -- this file
-- holds seed rows only. Runs inside a single `execute_sql` call.
--
-- Idempotency: the notebook re-runs this on every execution. We use
-- `ON CONFLICT DO NOTHING` so re-runs are safe -- rows keyed by `id`
-- are only inserted once.

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
    ('d10', 'shipping', 3, 'To track a shipment, open the order in Account > Orders and click the tracking number below the shipping address.')
ON CONFLICT (id) DO NOTHING;
