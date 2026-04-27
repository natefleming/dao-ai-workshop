USE IDENTIFIER(:database);

CREATE TABLE IF NOT EXISTS products (
  sku STRING NOT NULL,
  product_name STRING NOT NULL,
  category STRING NOT NULL,
  description STRING,
  price DOUBLE,
  in_stock BOOLEAN
) USING DELTA
TBLPROPERTIES (delta.enableChangeDataFeed = true);

INSERT INTO products (sku, product_name, category, description, price, in_stock) VALUES
  ('SKU-0001', 'Cordless Drill 20V', 'Power Tools', 'Compact cordless drill with 20V lithium battery, variable speed trigger, and LED light.', 49.99, true),
  ('SKU-0002', 'Claw Hammer 16oz', 'Hand Tools', 'Fiberglass handle claw hammer, 16oz head, anti-vibration grip.', 18.95, true),
  ('SKU-0003', 'Interior Latex Paint - White', 'Paint', 'Premium interior latex paint, eggshell finish, low VOC, 1 gallon.', 34.99, true),
  ('SKU-0004', 'Deck Screws #8 x 2.5"', 'Hardware', 'Coated deck screws, star drive, 1 lb box (~100 screws).', 8.49, false),
  ('SKU-0005', 'Pipe Wrench 14"', 'Plumbing', 'Heavy-duty cast iron pipe wrench, 14 inch, adjustable jaw.', 27.50, true),
  ('SKU-0006', 'Wire Stripper', 'Electrical', 'Self-adjusting wire stripper for 10-24 AWG, ergonomic handle.', 15.99, true),
  ('SKU-0007', 'Garden Hose 50ft', 'Lawn & Garden', 'Kink-resistant garden hose, 50 foot, brass fittings, 5/8 inch diameter.', 29.99, true),
  ('SKU-0008', 'Circular Saw 7.25"', 'Power Tools', 'Corded circular saw, 15 amp motor, 7.25 inch blade, bevel capacity 0-56 degrees.', 89.99, true),
  ('SKU-0009', 'Screwdriver Set 10pc', 'Hand Tools', 'Phillips and flathead screwdriver set, magnetic tips, comfort grip handles.', 14.99, true),
  ('SKU-0010', 'Exterior Stain - Cedar', 'Paint', 'Semi-transparent exterior wood stain, cedar tone, UV protection, 1 gallon.', 42.99, false),
  ('SKU-0011', 'Drywall Anchors 50pk', 'Hardware', 'Self-drilling drywall anchors with screws, holds up to 75 lbs, 50 pack.', 6.99, true),
  ('SKU-0012', 'Basin Wrench', 'Plumbing', 'Telescoping basin wrench for faucet installation, 10-17 inch reach.', 19.99, true),
  ('SKU-0013', 'GFCI Outlet', 'Electrical', 'Ground fault circuit interrupter outlet, 15 amp, tamper-resistant, white.', 12.49, true),
  ('SKU-0014', 'Pruning Shears', 'Lawn & Garden', 'Bypass pruning shears, hardened steel blade, cuts up to 3/4 inch branches.', 16.99, true),
  ('SKU-0015', 'Jigsaw Variable Speed', 'Power Tools', 'Orbital action jigsaw, 6.5 amp, variable speed, tool-free blade change.', 64.99, true),
  ('SKU-0016', 'Tape Measure 25ft', 'Hand Tools', 'Self-locking tape measure, 25 foot, 1 inch wide blade, belt clip.', 11.99, true),
  ('SKU-0017', 'Spray Paint - Gloss Black', 'Paint', 'All-purpose spray paint, gloss black, fast dry, 12 oz can.', 5.49, true),
  ('SKU-0018', 'Assorted Nails 5lb', 'Hardware', 'Assorted common nails, 2d through 16d, 5 lb box.', 12.99, false),
  ('SKU-0019', 'Teflon Tape', 'Plumbing', 'PTFE thread seal tape, 1/2 inch x 520 inch, 3 pack.', 3.99, true),
  ('SKU-0020', 'Wire Nuts Assorted 100pk', 'Electrical', 'Twist-on wire connectors, assorted sizes, 100 pack.', 7.99, true),
  ('SKU-0021', 'Lawn Mower Electric 21"', 'Lawn & Garden', 'Cordless electric lawn mower, 21 inch deck, 56V battery, mulch and bag.', 349.99, true),
  ('SKU-0022', 'Orbital Sander 5"', 'Power Tools', 'Random orbital sander, 3 amp, 5 inch pad, variable speed, dust collection.', 54.99, true),
  ('SKU-0023', 'Adjustable Wrench 10"', 'Hand Tools', 'Chrome vanadium adjustable wrench, 10 inch, wide jaw opening.', 13.49, true),
  ('SKU-0024', 'Primer - White', 'Paint', 'Interior/exterior multi-surface primer, white, 1 quart.', 14.99, true),
  ('SKU-0025', 'Cabinet Hinges 10pk', 'Hardware', 'Soft-close cabinet hinges, nickel finish, full overlay, 10 pack.', 22.99, true),
  ('SKU-0026', 'Plunger Heavy Duty', 'Plumbing', 'Flange plunger for toilets, heavy duty rubber cup, T-handle.', 9.99, true),
  ('SKU-0027', 'Outlet Cover Plates 10pk', 'Electrical', 'Standard outlet wall plates, white, unbreakable nylon, 10 pack.', 5.99, false),
  ('SKU-0028', 'Wheelbarrow 6 cu ft', 'Lawn & Garden', 'Steel tray wheelbarrow, 6 cubic foot capacity, pneumatic tire.', 89.99, true),
  ('SKU-0029', 'Impact Driver 20V', 'Power Tools', 'Cordless impact driver, 20V, 1/4 inch hex chuck, 1500 in-lbs torque.', 79.99, true),
  ('SKU-0030', 'Level 48"', 'Hand Tools', 'Aluminum box beam level, 48 inch, 3 vials, shock-absorbing end caps.', 34.99, true);
