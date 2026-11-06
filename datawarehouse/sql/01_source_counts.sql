-- Source counts reconciliation queries for validation

-- MySQL source counts (to be run on RDS)
SELECT 'customers' as entity, COUNT(*) as source_count FROM customers
UNION ALL
SELECT 'products', COUNT(*) FROM products
UNION ALL
SELECT 'orders', COUNT(*) FROM orders
UNION ALL
SELECT 'order_items', COUNT(*) FROM order_items;

-- DocumentDB source counts (to be run on DocumentDB via mongo shell)
-- db.reviews.countDocuments()
-- db.navigation_events.countDocuments()

-- Redshift raw counts (run in Redshift)
SELECT 'mysql_customers' as entity, COUNT(*) as raw_count FROM "raw".mysql_customers
UNION ALL
SELECT 'mysql_products', COUNT(*) FROM "raw".mysql_products
UNION ALL
SELECT 'mysql_orders', COUNT(*) FROM "raw".mysql_orders
UNION ALL
SELECT 'mysql_order_items', COUNT(*) FROM "raw".mysql_order_items
UNION ALL
SELECT 'mongo_reviews', COUNT(*) FROM "raw".mongo_reviews
UNION ALL
SELECT 'mongo_navigation_events', COUNT(*) FROM "raw".mongo_navigation_events;