USE IDENTIFIER(:database);

CREATE OR REPLACE VIEW active_products_v (
  sku COMMENT 'Stock-keeping unit identifier',
  product_name COMMENT 'Human-readable product display name',
  category COMMENT 'Product department',
  description COMMENT 'Detailed product description',
  price COMMENT 'Current retail price in USD',
  in_stock COMMENT 'True if available for purchase'
)
COMMENT 'Active products only. Filters the products table to status = ACTIVE, excluding discontinued items.'
AS
SELECT sku, product_name, category, description, price, in_stock
FROM products
WHERE status = 'ACTIVE';
