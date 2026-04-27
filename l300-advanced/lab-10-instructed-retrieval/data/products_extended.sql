USE IDENTIFIER(:database);

-- Lab 10's products table extends Lab 2's schema with metadata columns
-- the instructed retriever uses as filter dimensions: brand_name,
-- price_tier, sku_prefix, weight_lbs.
--
-- Single-file DROP + CREATE + INSERT for full idempotency on re-runs.

DROP TABLE IF EXISTS products;

CREATE TABLE products (
  sku STRING NOT NULL,
  product_name STRING NOT NULL,
  category STRING NOT NULL,
  description STRING,
  price DOUBLE,
  in_stock BOOLEAN,
  brand_name STRING COMMENT 'Brand / manufacturer (e.g. MILWAUKEE, DEWALT)',
  price_tier STRING COMMENT 'budget | mid | premium based on price band',
  sku_prefix STRING COMMENT 'First 3 characters of SKU (a coarse category bucket)',
  weight_lbs DOUBLE COMMENT 'Estimated shipping weight in pounds'
) USING DELTA
TBLPROPERTIES (delta.enableChangeDataFeed = true);

INSERT INTO products (sku, product_name, category, description, price, in_stock, brand_name, price_tier, sku_prefix, weight_lbs) VALUES
  ('SKU-0001', 'Cordless Drill 20V', 'Power Tools', 'Compact cordless drill with 20V lithium battery, variable speed trigger, and LED light.', 49.99, true, 'MILWAUKEE', 'mid', 'SKU', 4.5),
  ('SKU-0002', 'Claw Hammer 16oz', 'Hand Tools', 'Fiberglass handle claw hammer, 16oz head, anti-vibration grip.', 18.95, true, 'STANLEY', 'mid', 'SKU', 1.3),
  ('SKU-0003', 'Interior Latex Paint - White', 'Paint', 'Premium interior latex paint, eggshell finish, low VOC, 1 gallon.', 34.99, true, 'BENJAMIN-MOORE', 'mid', 'SKU', 10.0),
  ('SKU-0004', 'Deck Screws #8 x 2.5"', 'Hardware', 'Coated deck screws, star drive, 1 lb box (~100 screws).', 8.49, false, 'GENERIC', 'budget', 'SKU', 1.0),
  ('SKU-0005', 'Pipe Wrench 14"', 'Plumbing', 'Heavy-duty cast iron pipe wrench, 14 inch, adjustable jaw.', 27.50, true, 'RIDGID', 'mid', 'SKU', 1.5),
  ('SKU-0006', 'Wire Stripper', 'Electrical', 'Self-adjusting wire stripper for 10-24 AWG, ergonomic handle.', 15.99, true, 'KLEIN', 'mid', 'SKU', 0.3),
  ('SKU-0007', 'Garden Hose 50ft', 'Lawn & Garden', 'Kink-resistant garden hose, 50 foot, brass fittings, 5/8 inch diameter.', 29.99, true, 'TORO', 'mid', 'SKU', 8.0),
  ('SKU-0008', 'Circular Saw 7.25"', 'Power Tools', 'Corded circular saw, 15 amp motor, 7.25 inch blade, bevel capacity 0-56 degrees.', 89.99, true, 'MILWAUKEE', 'premium', 'SKU', 6.5),
  ('SKU-0009', 'Screwdriver Set 10pc', 'Hand Tools', 'Phillips and flathead screwdriver set, magnetic tips, comfort grip handles.', 14.99, true, 'STANLEY', 'budget', 'SKU', 1.1),
  ('SKU-0010', 'Exterior Stain - Cedar', 'Paint', 'Semi-transparent exterior wood stain, cedar tone, UV protection, 1 gallon.', 42.99, false, 'BENJAMIN-MOORE', 'mid', 'SKU', 10.0),
  ('SKU-0011', 'Drywall Anchors 50pk', 'Hardware', 'Self-drilling drywall anchors with screws, holds up to 75 lbs, 50 pack.', 6.99, true, 'GENERIC', 'budget', 'SKU', 1.0),
  ('SKU-0012', 'Basin Wrench', 'Plumbing', 'Telescoping basin wrench for faucet installation, 10-17 inch reach.', 19.99, true, 'RIDGID', 'mid', 'SKU', 1.5),
  ('SKU-0013', 'GFCI Outlet', 'Electrical', 'Ground fault circuit interrupter outlet, 15 amp, tamper-resistant, white.', 12.49, true, 'KLEIN', 'budget', 'SKU', 0.3),
  ('SKU-0014', 'Pruning Shears', 'Lawn & Garden', 'Bypass pruning shears, hardened steel blade, cuts up to 3/4 inch branches.', 16.99, true, 'TORO', 'mid', 'SKU', 6.7),
  ('SKU-0015', 'Jigsaw Variable Speed', 'Power Tools', 'Orbital action jigsaw, 6.5 amp, variable speed, tool-free blade change.', 64.99, true, 'DEWALT', 'mid', 'SKU', 5.2),
  ('SKU-0016', 'Tape Measure 25ft', 'Hand Tools', 'Self-locking tape measure, 25 foot, 1 inch wide blade, belt clip.', 11.99, true, 'STANLEY', 'budget', 'SKU', 1.0),
  ('SKU-0017', 'Spray Paint - Gloss Black', 'Paint', 'All-purpose spray paint, gloss black, fast dry, 12 oz can.', 5.49, true, 'BENJAMIN-MOORE', 'budget', 'SKU', 10.0),
  ('SKU-0018', 'Lag Bolts 1/2x4 25pk', 'Hardware', 'Hex head lag bolts, zinc plated, 1/2 inch x 4 inch, 25 count.', 12.99, true, 'GENERIC', 'budget', 'SKU', 1.0),
  ('SKU-0019', 'Toilet Flapper', 'Plumbing', 'Universal toilet flapper, fits most 2 inch flush valves, chlorine resistant.', 7.99, true, 'RIDGID', 'budget', 'SKU', 1.5),
  ('SKU-0020', 'LED Bulb 60W Equiv 4pk', 'Electrical', 'A19 LED bulbs, 60 watt equivalent, soft white 2700K, 4 pack.', 9.99, true, 'KLEIN', 'budget', 'SKU', 0.3),
  ('SKU-0021', 'Rake Leaf Steel', 'Lawn & Garden', 'Steel leaf rake, 24 inch wide head, hardwood handle, 64 inch length.', 22.99, true, 'TORO', 'mid', 'SKU', 7.3),
  ('SKU-0022', 'Impact Driver 18V', 'Power Tools', 'Brushless 18V impact driver, 1500 in-lb torque, LED light, belt clip.', 119.99, true, 'DEWALT', 'premium', 'SKU', 8.0),
  ('SKU-0023', 'Adjustable Wrench 10"', 'Hand Tools', 'Chrome plated adjustable wrench, 10 inch, smooth jaw action.', 13.99, true, 'STANLEY', 'budget', 'SKU', 1.1),
  ('SKU-0024', 'Primer - Indoor White', 'Paint', 'Stain-blocking interior primer, low VOC, 1 gallon, white.', 26.99, true, 'BENJAMIN-MOORE', 'mid', 'SKU', 10.0),
  ('SKU-0025', 'Concrete Anchors 25pk', 'Hardware', 'Wedge anchors for concrete, 1/4 inch x 2.25 inch, 25 pack.', 11.49, true, 'GENERIC', 'budget', 'SKU', 1.0),
  ('SKU-0026', 'PEX Crimping Tool', 'Plumbing', 'PEX crimping tool with 1/2 inch and 3/4 inch jaws, ratcheting.', 79.99, false, 'RIDGID', 'premium', 'SKU', 1.5),
  ('SKU-0027', 'Outdoor Extension Cord 50ft', 'Electrical', 'Heavy-duty outdoor extension cord, 50 foot, 12 gauge, lighted ends.', 34.99, true, 'KLEIN', 'mid', 'SKU', 0.3),
  ('SKU-0028', 'Sprinkler Pulsating', 'Lawn & Garden', 'Pulsating impact sprinkler, brass head, covers up to 80 ft diameter.', 14.99, true, 'TORO', 'mid', 'SKU', 6.5),
  ('SKU-0029', 'Reciprocating Saw', 'Power Tools', 'Corded reciprocating saw, 12 amp, variable speed, tool-free blade change.', 79.99, true, 'MILWAUKEE', 'premium', 'SKU', 6.0),
  ('SKU-0030', 'Utility Knife', 'Hand Tools', 'Retractable utility knife with 5 blade storage, comfort grip.', 9.99, true, 'STANLEY', 'budget', 'SKU', 0.9);
