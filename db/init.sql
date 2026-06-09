-- Runs once on first MySQL container init (docker-entrypoint-initdb.d).
-- The MYSQL_USER (`pms`) already owns the app DB. pytest-django creates a
-- throwaway `test_<dbname>` database, so the app user also needs privileges
-- on databases matching `test_%` to create and tear those down.
GRANT ALL PRIVILEGES ON `test\_%`.* TO 'pms'@'%';
FLUSH PRIVILEGES;
