USE IDENTIFIER(:database);

CREATE OR REPLACE TABLE orders (
  order_id STRING NOT NULL COMMENT 'Unique order line identifier',
  sku STRING NOT NULL COMMENT 'Product SKU referencing the products table',
  qty INT NOT NULL COMMENT 'Quantity of items in this order line',
  amount DOUBLE NOT NULL COMMENT 'Total line amount in USD (qty * unit price)',
  order_date DATE NOT NULL COMMENT 'Date the order was placed',
  status STRING NOT NULL COMMENT 'Order status: COMPLETED, PENDING, or CANCELLED'
) USING DELTA
COMMENT 'Order line items for the hardware store. Each row is one product line within an order.'
TBLPROPERTIES (delta.enableChangeDataFeed = true);

INSERT INTO orders (order_id, sku, qty, amount, order_date, status) VALUES
  ('ORD-1001', 'SKU-0001', 2, 99.98,  '2025-04-01', 'COMPLETED'),
  ('ORD-1002', 'SKU-0003', 3, 104.97, '2025-04-02', 'COMPLETED'),
  ('ORD-1003', 'SKU-0008', 1, 89.99,  '2025-04-03', 'COMPLETED'),
  ('ORD-1004', 'SKU-0015', 1, 64.99,  '2025-04-04', 'COMPLETED'),
  ('ORD-1005', 'SKU-0001', 1, 49.99,  '2025-04-05', 'COMPLETED'),
  ('ORD-1006', 'SKU-0021', 1, 349.99, '2025-04-06', 'COMPLETED'),
  ('ORD-1007', 'SKU-0009', 4, 59.96,  '2025-04-07', 'COMPLETED'),
  ('ORD-1008', 'SKU-0002', 2, 37.90,  '2025-04-08', 'COMPLETED'),
  ('ORD-1009', 'SKU-0029', 1, 79.99,  '2025-04-09', 'COMPLETED'),
  ('ORD-1010', 'SKU-0005', 1, 27.50,  '2025-04-10', 'COMPLETED'),
  ('ORD-1011', 'SKU-0022', 2, 109.98, '2025-04-11', 'COMPLETED'),
  ('ORD-1012', 'SKU-0007', 3, 89.97,  '2025-04-12', 'COMPLETED'),
  ('ORD-1013', 'SKU-0016', 5, 59.95,  '2025-04-13', 'COMPLETED'),
  ('ORD-1014', 'SKU-0001', 3, 149.97, '2025-04-14', 'COMPLETED'),
  ('ORD-1015', 'SKU-0017', 10, 54.90, '2025-04-15', 'COMPLETED'),
  ('ORD-1016', 'SKU-0025', 2, 45.98,  '2025-04-16', 'COMPLETED'),
  ('ORD-1017', 'SKU-0013', 6, 74.94,  '2025-04-17', 'COMPLETED'),
  ('ORD-1018', 'SKU-0019', 8, 31.92,  '2025-04-18', 'COMPLETED'),
  ('ORD-1019', 'SKU-0028', 1, 89.99,  '2025-04-19', 'COMPLETED'),
  ('ORD-1020', 'SKU-0014', 3, 50.97,  '2025-04-20', 'COMPLETED'),
  ('ORD-1021', 'SKU-0008', 2, 179.98, '2025-04-21', 'COMPLETED'),
  ('ORD-1022', 'SKU-0006', 4, 63.96,  '2025-04-22', 'COMPLETED'),
  ('ORD-1023', 'SKU-0003', 1, 34.99,  '2025-04-23', 'COMPLETED'),
  ('ORD-1024', 'SKU-0012', 2, 39.98,  '2025-04-24', 'COMPLETED'),
  ('ORD-1025', 'SKU-0011', 10, 69.90, '2025-04-25', 'COMPLETED'),
  ('ORD-1026', 'SKU-0029', 2, 159.98, '2025-04-26', 'COMPLETED'),
  ('ORD-1027', 'SKU-0024', 4, 59.96,  '2025-04-27', 'COMPLETED'),
  ('ORD-1028', 'SKU-0020', 6, 47.94,  '2025-04-28', 'COMPLETED'),
  ('ORD-1029', 'SKU-0023', 2, 26.98,  '2025-04-29', 'COMPLETED'),
  ('ORD-1030', 'SKU-0026', 3, 29.97,  '2025-04-30', 'COMPLETED');
