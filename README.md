# Architecture
SimpleRDBMS
├── Table Management
│   ├── CREATE TABLE
│   ├── DROP TABLE
│   └── Schema validation
├── Data Operations
│   ├── INSERT with validation
│   ├── SELECT with WHERE/ORDER BY
│   ├── UPDATE with constraints
│   └── DELETE with conditions
├── Index System
│   ├── Primary key indexes
│   ├── Unique constraint indexes
│   └── Custom multi-column indexes
├── Transaction Support
│   ├── BEGIN TRANSACTION
│   ├── COMMIT
│   └── ROLLBACK
└── Storage
    ├── Pickle-based serialization
    └── File-based persistence

#    How to Use the System
Option 1: Interactive SQL REPL

# Run the REPL
python3 rdbms.py

# Example SQL commands in REPL:
SQL> CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE)
SQL> INSERT INTO users VALUES (1, 'Alice', 'alice@example.com')
SQL> SELECT * FROM users
SQL> CREATE INDEX idx_email ON users (email)
SQL> UPDATE users SET name = 'Alice Smith' WHERE id = 1
SQL> DELETE FROM users WHERE id = 1
SQL> TABLES  # Show all tables

Option 2: Web Interface

# Start web interface
python3 rdbms.py --web
# Open http://localhost:8080 in browser

Option 3: Todo App Demo

# Run the todo app
python3 todo_app.py
# Open http://localhost:8000 in browser