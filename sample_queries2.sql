SELECT * FROM users;

SELECT * FROM orders WHERE status = 'PENDING';

SELECT * FROM transactions WHERE amount > 5000;

SELECT * FROM products JOIN categories ON products.cat_id = categories.id;

SELECT * FROM employees WHERE department_id = 4;

SELECT * FROM logs WHERE severity = 'ERROR';

SELECT * FROM inventory WHERE stock_qty < 10;

SELECT * FROM invoices WHERE paid_status = 0;

SELECT * FROM customers WHERE country = 'India';

SELECT * FROM audit_trail WHERE action_date >= '2025-01-01';

-- CATEGORY 2: NON-SARGABLE LEADING WILDCARDS (Queries 11-20)

SELECT id, email FROM users WHERE email LIKE '%gmail.com';

SELECT product_name, sku FROM inventory WHERE sku LIKE '%-X99';

SELECT first_name, last_name FROM employees WHERE phone_number LIKE '%9876';

SELECT order_id, notes FROM orders WHERE notes '%urgent%';

SELECT title, description FROM articles WHERE body LIKE '%database%';

SELECT company_name FROM clients WHERE website LIKE '%org';

SELECT street_address FROM locations WHERE zip_code LIKE '%1100';

SELECT username FROM accounts WHERE handle LIKE '%admin%';

SELECT trans_ref FROM payments WHERE gateway_response LIKE '%timeout%';

SELECT error_msg FROM server_logs WHERE stack_trace LIKE '%NullPointerException%';

-- CATEGORY 3: MISSING PAGINATION & LIMIT CLAUSES (Queries 21-35)

SELECT customer_id, balance FROM accounts ORDER BY balance DESC;

SELECT item_id, price FROM catalog ORDER BY price ASC;

SELECT student_id, cgpa FROM academics ORDER BY cgpa DESC;

SELECT post_id, views FROM blog_posts ORDER BY views DESC;

SELECT ticket_id, priority FROM support_tickets ORDER BY created_at ASC;

SELECT driver_id, rating FROM drivers ORDER BY rating DESC;

SELECT hotel_id, nightly_rate FROM hotels ORDER BY nightly_rate ASC;

SELECT flight_id, departure_time FROM flights ORDER BY departure_time ASC;

SELECT movie_id, release_year FROM movies ORDER BY release_year DESC;

SELECT book_id, rating FROM library ORDER BY rating DESC;

SELECT patient_id, admission_date FROM hospital_records ORDER BY admission_date DESC;

SELECT property_id, square_feet FROM real_estate ORDER BY square_feet DESC;

SELECT candidate_id, experience_years FROM resumes ORDER BY experience_years DESC;

SELECT song_id, stream_count FROM music_tracks ORDER BY stream_count DESC;

SELECT merchant_id, total_sales FROM merchants ORDER BY total_sales DESC;

-- CATEGORY 4: UNINDEXED JOINS & COMPLEX CARTESIAN SPIKES (Queries 36-50)

SELECT u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id WHERE o.total > 1000;

SELECT c.name, p.product_name FROM customers c JOIN payments p ON c.id = p.customer_id ORDER BY p.payment_date;

SELECT e.emp_name, d.dept_name FROM employees e JOIN departments d ON e.dept_id = d.id WHERE d.location = 'New York';

SELECT s.school_name, t.teacher_name FROM schools s JOIN teachers t ON s.id = t.school_id ORDER BY t.salary DESC;

SELECT a.author_name, b.book_title FROM authors a JOIN books b ON a.id = b.author_id WHERE b.genre = 'Sci-Fi';

SELECT car.model, r.rental_date FROM cars car JOIN rentals r ON car.id = r.car_id ORDER BY r.rental_date DESC;

SELECT p.patient_name, d.doctor_name FROM patients p JOIN appointments app ON p.id = app.patient_id JOIN doctors d ON app.doctor_id = d.id;

SELECT o.order_id, i.item_name FROM orders o JOIN order_items oi ON o.id = oi.order_id JOIN items i ON oi.item_id = i.id;

SELECT c.company_name, proj.project_name FROM clients c JOIN contracts con ON c.id = con.client_id JOIN projects proj ON con.project_id = proj.id;

SELECT st.student_name, sub.subject_name FROM students st JOIN enrollments en ON st.id = en.student_id JOIN subjects sub ON en.subject_id = sub.id ORDER BY st.student_name;

SELECT v.vendor_name, po.po_number FROM vendors v JOIN purchase_orders po ON v.id = po.vendor_id WHERE po.status = 'APPROVED';

SELECT w.warehouse_name, stock.item_id FROM warehouses w JOIN stock_levels stock ON w.id = stock.warehouse_id ORDER BY stock.quantity ASC;

SELECT t.team_name, p.player_name FROM teams t JOIN players p ON t.id = p.team_id WHERE p.is_active = 1;

SELECT sub.subscriber_email, sub_plan.plan_name FROM subscribers sub JOIN subscriptions sub_plan ON sub.id = sub_plan.subscriber_id ORDER BY sub_plan.start_date DESC;

SELECT * FROM transactions t JOIN accounts a ON t.account_id = a.id JOIN branches b ON a.branch_id = b.id WHERE t.status = 'FAILED';