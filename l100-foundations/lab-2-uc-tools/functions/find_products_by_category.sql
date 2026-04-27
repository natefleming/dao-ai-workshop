CREATE OR REPLACE FUNCTION {catalog_name}.{schema_name}.find_products_by_category(
  category STRING COMMENT 'Product category (e.g. "Power Tools", "Paint", "Hardware")'
)
RETURNS TABLE (
  sku STRING,
  product_name STRING,
  category STRING,
  price DOUBLE,
  in_stock BOOLEAN
)
READS SQL DATA
COMMENT 'List products in a given category, ordered by price ascending. Returns up to 10 rows.'
RETURN
  SELECT p.sku, p.product_name, p.category, p.price, p.in_stock
  FROM {catalog_name}.{schema_name}.products p
  WHERE lower(p.category) = lower(find_products_by_category.category)
  ORDER BY p.price ASC
  LIMIT 10;
