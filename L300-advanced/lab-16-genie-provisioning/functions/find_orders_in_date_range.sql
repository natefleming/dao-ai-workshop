CREATE OR REPLACE FUNCTION {catalog_name}.{schema_name}.find_orders_in_date_range(
  start_date STRING COMMENT 'Start of the date range (inclusive), ISO format YYYY-MM-DD',
  end_date STRING COMMENT 'End of the date range (inclusive), ISO format YYYY-MM-DD'
)
RETURNS TABLE (
  order_id STRING COMMENT 'Unique order line identifier',
  sku STRING COMMENT 'Product SKU referencing the products table',
  qty INT COMMENT 'Quantity of items in this order line',
  amount DOUBLE COMMENT 'Total line amount in USD',
  order_date DATE COMMENT 'Date the order was placed',
  status STRING COMMENT 'Order status: COMPLETED, PENDING, or CANCELLED'
)
READS SQL DATA
COMMENT 'Return orders within a date range. Useful for sales analysis over a specific window.'
RETURN
  SELECT order_id, sku, qty, amount, order_date, status
  FROM {catalog_name}.{schema_name}.orders
  WHERE order_date BETWEEN CAST(find_orders_in_date_range.start_date AS DATE)
                       AND CAST(find_orders_in_date_range.end_date AS DATE)
  ORDER BY order_date;
