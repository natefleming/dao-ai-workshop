CREATE OR REPLACE FUNCTION {catalog_name}.{schema_name}.find_products_by_tier(
  category STRING COMMENT 'Product category (e.g. "Power Tools", "Paint", "Hardware")',
  customer_tier STRING COMMENT 'Loyalty tier: bronze | silver | gold | platinum (controls price ceiling)'
)
RETURNS TABLE (
  sku STRING,
  product_name STRING,
  category STRING,
  price DOUBLE,
  tier_match STRING,
  in_stock BOOLEAN
)
READS SQL DATA
COMMENT 'List products in a category whose price fits the customer''s loyalty tier. bronze<=50, silver<=150, gold<=400, platinum unlimited.'
RETURN
  SELECT
    p.sku,
    p.product_name,
    p.category,
    p.price,
    -- Tier-fit label so the agent can explain why it returned each row.
    CASE
      WHEN lower(find_products_by_tier.customer_tier) = 'platinum' THEN 'all-tiers'
      WHEN lower(find_products_by_tier.customer_tier) = 'gold'     AND p.price <= 400 THEN 'gold-fit'
      WHEN lower(find_products_by_tier.customer_tier) = 'silver'   AND p.price <= 150 THEN 'silver-fit'
      WHEN lower(find_products_by_tier.customer_tier) = 'bronze'   AND p.price <=  50 THEN 'bronze-fit'
      ELSE 'over-tier'
    END AS tier_match,
    p.in_stock
  FROM {catalog_name}.{schema_name}.products p
  WHERE lower(p.category) = lower(find_products_by_tier.category)
    AND p.price <= CASE lower(find_products_by_tier.customer_tier)
                     WHEN 'bronze'   THEN 50
                     WHEN 'silver'   THEN 150
                     WHEN 'gold'     THEN 400
                     WHEN 'platinum' THEN 1.0e9
                     ELSE 1.0e9
                   END
  ORDER BY p.price ASC
  LIMIT 10;
