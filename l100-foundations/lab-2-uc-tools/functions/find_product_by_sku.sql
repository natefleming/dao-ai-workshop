CREATE OR REPLACE FUNCTION {catalog_name}.{schema_name}.find_product_by_sku(
  sku ARRAY<STRING> COMMENT 'One or more product SKUs to look up'
)
RETURNS TABLE (
  sku STRING,
  product_name STRING,
  category STRING,
  price DOUBLE,
  in_stock BOOLEAN
)
READS SQL DATA
COMMENT 'Look up one or more products by SKU. Returns product name, category, price, and stock flag.'
RETURN
  SELECT sku, product_name, category, price, in_stock
  FROM {catalog_name}.{schema_name}.products
  WHERE ARRAY_CONTAINS(find_product_by_sku.sku, sku);
