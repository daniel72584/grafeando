CREATE TABLE users (
    id INT PRIMARY KEY,
    name VARCHAR(100)
);

CREATE TABLE orders (
    id INT PRIMARY KEY,
    user_id INT REFERENCES users(id),
    amount DECIMAL(10, 2)
);

SELECT o.id, u.name FROM orders o JOIN users u ON o.user_id = u.id;
