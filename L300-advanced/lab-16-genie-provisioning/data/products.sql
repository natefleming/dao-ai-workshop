USE IDENTIFIER(:database);

-- Idempotent DDL: CREATE IF NOT EXISTS + MERGE by primary key `sku`.
-- Rerunning does NOT drop the table, so any Vector Search index built off
-- the Change Data Feed continues to sync incrementally instead of being
-- invalidated. ``status`` and ``internal_notes`` are declared nullable so
-- a later 6-column INSERT from Lab 2 / 4 / 13 / 14 still succeeds against
-- the same table.

CREATE TABLE IF NOT EXISTS products (
  sku STRING NOT NULL COMMENT 'Stock-keeping unit identifier, unique per product',
  product_name STRING NOT NULL COMMENT 'Human-readable product display name',
  category STRING NOT NULL COMMENT 'Product department (e.g. Power Tools, Paint, Hardware)',
  description STRING COMMENT 'Detailed product description including specs and features',
  price DOUBLE COMMENT 'Current retail price in USD',
  in_stock BOOLEAN COMMENT 'True if the product is currently available for purchase',
  status STRING COMMENT 'Product lifecycle status: ACTIVE or DISCONTINUED',
  internal_notes STRING COMMENT 'Internal merchandising notes, not customer-facing'
) USING DELTA
COMMENT 'Product catalog for the hardware store. Each row is one SKU with pricing, stock, and lifecycle status.'
TBLPROPERTIES (delta.enableChangeDataFeed = true);

-- If Lab 11 (or any earlier lab that used a 6-col CREATE) beat us to the
-- table, add the two Lab 16 columns idempotently before MERGE runs.
ALTER TABLE products ADD COLUMNS IF NOT EXISTS (
  status STRING COMMENT 'Product lifecycle status: ACTIVE or DISCONTINUED',
  internal_notes STRING COMMENT 'Internal merchandising notes, not customer-facing'
);

MERGE INTO products t
USING (
  SELECT * FROM (VALUES
    ('SKU-0001', 'Cordless Drill 20V', 'Power Tools', 'Compact cordless drill with 20V lithium battery, variable speed trigger, and LED light.', 49.99, true, 'ACTIVE', 'Top seller Q1'),
    ('SKU-0002', 'Claw Hammer 16oz', 'Hand Tools', 'Fiberglass handle claw hammer, 16oz head, anti-vibration grip.', 18.95, true, 'ACTIVE', NULL),
    ('SKU-0003', 'Interior Latex Paint - White', 'Paint', 'Premium interior latex paint, eggshell finish, low VOC, 1 gallon.', 34.99, true, 'ACTIVE', NULL),
    ('SKU-0004', 'Deck Screws #8 x 2.5"', 'Hardware', 'Coated deck screws, star drive, 1 lb box (~100 screws).', 8.49, false, 'ACTIVE', 'Restock pending'),
    ('SKU-0005', 'Pipe Wrench 14"', 'Plumbing', 'Heavy-duty cast iron pipe wrench, 14 inch, adjustable jaw.', 27.50, true, 'ACTIVE', NULL),
    ('SKU-0006', 'Wire Stripper', 'Electrical', 'Self-adjusting wire stripper for 10-24 AWG, ergonomic handle.', 15.99, true, 'ACTIVE', NULL),
    ('SKU-0007', 'Garden Hose 50ft', 'Lawn & Garden', 'Kink-resistant garden hose, 50 foot, brass fittings, 5/8 inch diameter.', 29.99, true, 'ACTIVE', NULL),
    ('SKU-0008', 'Circular Saw 7.25"', 'Power Tools', 'Corded circular saw, 15 amp motor, 7.25 inch blade, bevel capacity 0-56 degrees.', 89.99, true, 'ACTIVE', NULL),
    ('SKU-0009', 'Screwdriver Set 10pc', 'Hand Tools', 'Phillips and flathead screwdriver set, magnetic tips, comfort grip handles.', 14.99, true, 'ACTIVE', NULL),
    ('SKU-0010', 'Exterior Stain - Cedar', 'Paint', 'Semi-transparent exterior wood stain, cedar tone, UV protection, 1 gallon.', 42.99, false, 'DISCONTINUED', 'Replaced by SKU-0030'),
    ('SKU-0011', 'Drywall Anchors 50pk', 'Hardware', 'Self-drilling drywall anchors with screws, holds up to 75 lbs, 50 pack.', 6.99, true, 'ACTIVE', NULL),
    ('SKU-0012', 'Basin Wrench', 'Plumbing', 'Telescoping basin wrench for faucet installation, 10-17 inch reach.', 19.99, true, 'ACTIVE', NULL),
    ('SKU-0013', 'GFCI Outlet', 'Electrical', 'Ground fault circuit interrupter outlet, 15 amp, tamper-resistant, white.', 12.49, true, 'ACTIVE', NULL),
    ('SKU-0014', 'Pruning Shears', 'Lawn & Garden', 'Bypass pruning shears, hardened steel blade, cuts up to 3/4 inch branches.', 16.99, true, 'ACTIVE', NULL),
    ('SKU-0015', 'Jigsaw Variable Speed', 'Power Tools', 'Orbital action jigsaw, 6.5 amp, variable speed, tool-free blade change.', 64.99, true, 'ACTIVE', NULL),
    ('SKU-0016', 'Tape Measure 25ft', 'Hand Tools', 'Self-locking tape measure, 25 foot, 1 inch wide blade, belt clip.', 11.99, true, 'ACTIVE', NULL),
    ('SKU-0017', 'Spray Paint - Gloss Black', 'Paint', 'All-purpose spray paint, gloss black, fast dry, 12 oz can.', 5.49, true, 'ACTIVE', NULL),
    ('SKU-0018', 'Assorted Nails 5lb', 'Hardware', 'Assorted common nails, 2d through 16d, 5 lb box.', 12.99, false, 'DISCONTINUED', 'Poor sales'),
    ('SKU-0019', 'Teflon Tape', 'Plumbing', 'PTFE thread seal tape, 1/2 inch x 520 inch, 3 pack.', 3.99, true, 'ACTIVE', NULL),
    ('SKU-0020', 'Wire Nuts Assorted 100pk', 'Electrical', 'Twist-on wire connectors, assorted sizes, 100 pack.', 7.99, true, 'ACTIVE', NULL),
    ('SKU-0021', 'Lawn Mower Electric 21"', 'Lawn & Garden', 'Cordless electric lawn mower, 21 inch deck, 56V battery, mulch and bag.', 349.99, true, 'ACTIVE', NULL),
    ('SKU-0022', 'Orbital Sander 5"', 'Power Tools', 'Random orbital sander, 3 amp, 5 inch pad, variable speed, dust collection.', 54.99, true, 'ACTIVE', NULL),
    ('SKU-0023', 'Adjustable Wrench 10"', 'Hand Tools', 'Chrome vanadium adjustable wrench, 10 inch, wide jaw opening.', 13.49, true, 'ACTIVE', NULL),
    ('SKU-0024', 'Primer - White', 'Paint', 'Interior/exterior multi-surface primer, white, 1 quart.', 14.99, true, 'ACTIVE', NULL),
    ('SKU-0025', 'Cabinet Hinges 10pk', 'Hardware', 'Soft-close cabinet hinges, nickel finish, full overlay, 10 pack.', 22.99, true, 'ACTIVE', NULL),
    ('SKU-0026', 'Plunger Heavy Duty', 'Plumbing', 'Flange plunger for toilets, heavy duty rubber cup, T-handle.', 9.99, true, 'ACTIVE', NULL),
    ('SKU-0027', 'Outlet Cover Plates 10pk', 'Electrical', 'Standard outlet wall plates, white, unbreakable nylon, 10 pack.', 5.99, false, 'ACTIVE', 'Restock pending'),
    ('SKU-0028', 'Wheelbarrow 6 cu ft', 'Lawn & Garden', 'Steel tray wheelbarrow, 6 cubic foot capacity, pneumatic tire.', 89.99, true, 'ACTIVE', NULL),
    ('SKU-0029', 'Impact Driver 20V', 'Power Tools', 'Cordless impact driver, 20V, 1/4 inch hex chuck, 1500 in-lbs torque.', 79.99, true, 'ACTIVE', NULL),
    ('SKU-0030', 'Exterior Stain - Redwood', 'Paint', 'Semi-transparent exterior wood stain, redwood tone, UV protection, 1 gallon.', 44.99, true, 'ACTIVE', 'Replaces SKU-0030')
  ) AS v(sku, product_name, category, description, price, in_stock, status, internal_notes)
) s
ON t.sku = s.sku
WHEN MATCHED THEN UPDATE SET
  product_name = s.product_name,
  category = s.category,
  description = s.description,
  price = s.price,
  in_stock = s.in_stock,
  status = s.status,
  internal_notes = s.internal_notes
WHEN NOT MATCHED THEN INSERT (sku, product_name, category, description, price, in_stock, status, internal_notes)
  VALUES (s.sku, s.product_name, s.category, s.description, s.price, s.in_stock, s.status, s.internal_notes);
