CREATE OR REPLACE FUNCTION {catalog_name}.{schema_name}.issue_refund(
  order_id STRING COMMENT 'Order identifier the refund applies to',
  amount DOUBLE COMMENT 'Refund amount in USD',
  reason STRING COMMENT 'Short rationale for the refund'
)
RETURNS STRING
COMMENT 'Issue a customer refund. High-stakes -- gated by human approval.'
RETURN
  'Refund of $' || CAST(amount AS STRING)
  || ' issued for order ' || order_id
  || ' (reason: ' || reason || ').';
