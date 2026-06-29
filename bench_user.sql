\set rid random(1, 1000000)
SELECT count(*), sum(amount) FROM events WHERE user_id = :rid;
