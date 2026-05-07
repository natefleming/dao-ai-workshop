USE IDENTIFIER(:database);

CREATE OR REPLACE VIEW daily_sales_mv (
  order_date COMMENT 'Calendar date of the sales activity',
  category COMMENT 'Product category for the aggregation',
  order_count COMMENT 'Number of distinct orders on this date for the category',
  total_units COMMENT 'Total quantity of items sold',
  total_revenue COMMENT 'Sum of order line amounts in USD'
)
COMMENT 'Pre-aggregated daily sales by product category. Joins orders to products and groups by date and category.'
AS
SELECT
  o.order_date,
  p.category,
  COUNT(DISTINCT o.order_id) AS order_count,
  SUM(o.qty) AS total_units,
  SUM(o.amount) AS total_revenue
FROM orders o
JOIN products p ON o.sku = p.sku
GROUP BY o.order_date, p.category;
