-- FasterQL Demo Query 1: E-Commerce Checkout Bottleneck
SELECT *
FROM orders
WHERE customer_email LIKE '%@enterprise.io'
  AND YEAR(created_at) = 2026
  AND user_id IN (
      SELECT id FROM users WHERE status = 'active'
  )
ORDER BY created_at DESC;

-- FasterQL Demo Query 2: Implicit Join + Case-Insensitive Function Trap
SELECT *
FROM users u, orders o, payments p
WHERE u.id = o.user_id
  AND o.id = p.order_id
  AND LOWER(u.email) = 'admin@company.org'
ORDER BY o.created_at DESC;
