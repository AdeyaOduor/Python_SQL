import json
import os
import re
import pickle
from datetime import datetime
from typing import Dict, List, Tuple, Any, Set, Optional
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum


class DataType(Enum):
    INTEGER = "INTEGER"
    TEXT = "TEXT"
    REAL = "REAL"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"


@dataclass
class Column:
    name: str
    data_type: DataType
    is_primary: bool = False
    is_unique: bool = False
    is_nullable: bool = True


@dataclass
class Index:
    column_names: List[str]
    entries: Dict[Tuple, List[int]] = field(default_factory=dict)


@dataclass
class Table:
    name: str
    columns: List[Column]
    rows: List[Dict[str, Any]] = field(default_factory=list)
    indexes: Dict[str, Index] = field(default_factory=dict)
    next_row_id: int = 1
    primary_key_column: Optional[Column] = None
    
    def __post_init__(self):
        for col in self.columns:
            if col.is_primary:
                self.primary_key_column = col
                break
        self._create_default_indexes()
    
    def _create_default_indexes(self):
        # Create index on primary key
        if self.primary_key_column:
            self.indexes["__primary"] = Index([self.primary_key_column.name])
        
        # Create indexes on unique columns
        for col in self.columns:
            if col.is_unique and col != self.primary_key_column:
                self.indexes[f"__unique_{col.name}"] = Index([col.name])
    
    def add_index(self, name: str, column_names: List[str]):
        self.indexes[name] = Index(column_names)
        self._rebuild_index(name)
    
    def _rebuild_index(self, index_name: str):
        if index_name in self.indexes:
            idx = self.indexes[index_name]
            idx.entries.clear()
            for i, row in enumerate(self.rows):
                key = tuple(row[col] for col in idx.column_names)
                if key not in idx.entries:
                    idx.entries[key] = []
                idx.entries[key].append(i)


class SimpleRDBMS:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.tables: Dict[str, Table] = {}
        self.transaction_log: List[str] = []
        self._in_transaction = False
        
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        
        self._load_tables()
    
    def _save_table(self, table_name: str):
        table = self.tables[table_name]
        with open(os.path.join(self.data_dir, f"{table_name}.pkl"), "wb") as f:
            pickle.dump(table, f)
    
    def _load_tables(self):
        for filename in os.listdir(self.data_dir):
            if filename.endswith(".pkl"):
                table_name = filename[:-4]
                with open(os.path.join(self.data_dir, filename), "rb") as f:
                    self.tables[table_name] = pickle.load(f)
    
    def execute_sql(self, sql: str) -> List[Dict[str, Any]]:
        sql = sql.strip().replace("\n", " ").replace("\t", " ")
        
        if self._in_transaction:
            self.transaction_log.append(sql)
        
        # Parse SQL
        sql_upper = sql.upper()
        
        # CREATE TABLE
        if sql_upper.startswith("CREATE TABLE"):
            return self._execute_create_table(sql)
        
        # INSERT
        elif sql_upper.startswith("INSERT"):
            return self._execute_insert(sql)
        
        # SELECT
        elif sql_upper.startswith("SELECT"):
            return self._execute_select(sql)
        
        # UPDATE
        elif sql_upper.startswith("UPDATE"):
            return self._execute_update(sql)
        
        # DELETE
        elif sql_upper.startswith("DELETE"):
            return self._execute_delete(sql)
        
        # DROP TABLE
        elif sql_upper.startswith("DROP TABLE"):
            return self._execute_drop_table(sql)
        
        # CREATE INDEX
        elif sql_upper.startswith("CREATE INDEX"):
            return self._execute_create_index(sql)
        
        # BEGIN TRANSACTION
        elif sql_upper.startswith("BEGIN TRANSACTION") or sql_upper.startswith("BEGIN"):
            self._begin_transaction()
            return [{"status": "Transaction started"}]
        
        # COMMIT
        elif sql_upper.startswith("COMMIT"):
            result = self._commit_transaction()
            return [{"status": "Transaction committed", "operations": len(result)}]
        
        # ROLLBACK
        elif sql_upper.startswith("ROLLBACK"):
            self._rollback_transaction()
            return [{"status": "Transaction rolled back"}]
        
        else:
            raise ValueError(f"Unsupported SQL command: {sql}")
    
    def _execute_create_table(self, sql: str) -> List[Dict[str, Any]]:
        pattern = r"CREATE TABLE (\w+)\s*\((.*)\)"
        match = re.match(pattern, sql, re.IGNORECASE | re.DOTALL)
        if not match:
            raise ValueError("Invalid CREATE TABLE syntax")
        
        table_name = match.group(1)
        columns_sql = match.group(2).strip()
        
        if table_name in self.tables:
            raise ValueError(f"Table '{table_name}' already exists")
        
        columns = []
        for col_def in columns_sql.split(","):
            col_def = col_def.strip()
            if not col_def:
                continue
            
            # Parse column definition
            parts = col_def.split()
            col_name = parts[0]
            data_type_str = parts[1].upper()
            
            data_type = DataType(data_type_str)
            
            is_primary = "PRIMARY KEY" in col_def.upper()
            is_unique = "UNIQUE" in col_def.upper() or is_primary
            is_nullable = "NOT NULL" not in col_def.upper()
            
            columns.append(Column(col_name, data_type, is_primary, is_unique, is_nullable))
        
        table = Table(table_name, columns)
        self.tables[table_name] = table
        self._save_table(table_name)
        
        return [{"status": f"Table '{table_name}' created successfully", "columns": len(columns)}]
    
    def _execute_insert(self, sql: str) -> List[Dict[str, Any]]:
        pattern = r"INSERT INTO (\w+)\s*(?:\(([^)]+)\))?\s*VALUES\s*\(([^)]+)\)"
        match = re.match(pattern, sql, re.IGNORECASE)
        if not match:
            raise ValueError("Invalid INSERT syntax")
        
        table_name = match.group(1)
        columns_str = match.group(2)
        values_str = match.group(3)
        
        if table_name not in self.tables:
            raise ValueError(f"Table '{table_name}' does not exist")
        
        table = self.tables[table_name]
        
        # Parse columns
        if columns_str:
            col_names = [c.strip() for c in columns_str.split(",")]
        else:
            col_names = [col.name for col in table.columns]
        
        # Parse values
        values = []
        for v in values_str.split(","):
            v = v.strip().strip("'")
            
            # Try to infer type
            if v.isdigit():
                values.append(int(v))
            elif v.replace('.', '', 1).isdigit():
                values.append(float(v))
            elif v.upper() in ('TRUE', 'FALSE'):
                values.append(v.upper() == 'TRUE')
            elif v == 'NULL':
                values.append(None)
            else:
                values.append(v)
        
        if len(col_names) != len(values):
            raise ValueError("Column count doesn't match value count")
        
        # Create row
        row = {}
        for col_name, value in zip(col_names, values):
            row[col_name] = value
        
        # Validate row
        self._validate_row(table, row)
        
        # Add row
        table.rows.append(row)
        
        # Update indexes
        for idx in table.indexes.values():
            key = tuple(row[col] for col in idx.column_names if col in row)
            if key not in idx.entries:
                idx.entries[key] = []
            idx.entries[key].append(len(table.rows) - 1)
        
        self._save_table(table_name)
        
        return [{"status": "Row inserted successfully", "row_id": len(table.rows)}]
    
    def _validate_row(self, table: Table, row: Dict[str, Any]):
        for col in table.columns:
            if col.name not in row:
                if not col.is_nullable:
                    raise ValueError(f"Column '{col.name}' cannot be NULL")
                continue
            
            value = row[col.name]
            
            # Type checking
            if value is not None:
                if col.data_type == DataType.INTEGER and not isinstance(value, int):
                    raise ValueError(f"Column '{col.name}' expects INTEGER")
                elif col.data_type == DataType.REAL and not isinstance(value, (int, float)):
                    raise ValueError(f"Column '{col.name}' expects REAL")
                elif col.data_type == DataType.BOOLEAN and not isinstance(value, bool):
                    raise ValueError(f"Column '{col.name}' expects BOOLEAN")
            
            # Unique constraint
            if col.is_unique and value is not None:
                for existing_row in table.rows:
                    if existing_row.get(col.name) == value:
                        raise ValueError(f"Duplicate value for unique column '{col.name}'")
    
    def _execute_select(self, sql: str) -> List[Dict[str, Any]]:
        # Simple SELECT parsing (no subqueries, limited joins)
        pattern = r"SELECT (.+?) FROM (.+?)(?: WHERE (.+?))?(?: ORDER BY (.+?))?$"
        match = re.match(pattern, sql, re.IGNORECASE)
        if not match:
            raise ValueError("Invalid SELECT syntax")
        
        select_clause = match.group(1).strip()
        from_clause = match.group(2).strip()
        where_clause = match.group(3)
        order_clause = match.group(4)
        
        # Parse tables (simple join support)
        tables = []
        join_info = []
        
        if " JOIN " in from_clause.upper():
            # Simple join parsing
            parts = re.split(r'\s+JOIN\s+', from_clause, flags=re.IGNORECASE)
            for part in parts:
                if " ON " in part.upper():
                    table_part, condition = part.split(" ON ", 1)
                    tables.append(table_part.strip())
                    join_info.append(condition.strip())
                else:
                    tables.append(part.strip())
        else:
            tables.append(from_clause)
        
        # Get table objects
        table_objs = []
        for table_name in tables:
            if table_name not in self.tables:
                raise ValueError(f"Table '{table_name}' does not exist")
            table_objs.append(self.tables[table_name])
        
        # Parse columns
        if select_clause == "*":
            columns = [col.name for col in table_objs[0].columns]
        else:
            columns = [col.strip() for col in select_clause.split(",")]
        
        # Get rows from first table
        results = []
        if len(table_objs) == 1:
            # Single table query
            for row in table_objs[0].rows:
                results.append(row.copy())
        else:
            # Join tables (simple nested loop join)
            for row1 in table_objs[0].rows:
                for row2 in table_objs[1].rows:
                    joined_row = {**row1, **{f"{tables[1]}.{k}": v for k, v in row2.items()}}
                    results.append(joined_row)
        
        # Apply WHERE clause
        if where_clause:
            filtered_results = []
            for row in results:
                if self._evaluate_where(row, where_clause):
                    filtered_results.append(row)
            results = filtered_results
        
        # Apply ORDER BY
        if order_clause:
            order_cols = [col.strip() for col in order_clause.split(",")]
            results.sort(key=lambda x: tuple(x.get(col, "") for col in order_cols))
        
        # Select only requested columns
        final_results = []
        for row in results:
            final_row = {}
            for col in columns:
                if col in row:
                    final_row[col] = row[col]
                elif "." in col:
                    # Handle table.column format
                    final_row[col] = row.get(col, None)
            final_results.append(final_row)
        
        return final_results
    
    def _evaluate_where(self, row: Dict[str, Any], condition: str) -> bool:
        # Simple WHERE evaluation
        condition = condition.strip()
        
        # Handle AND/OR
        if " AND " in condition.upper():
            parts = re.split(r'\s+AND\s+', condition, flags=re.IGNORECASE)
            return all(self._evaluate_where(row, part) for part in parts)
        elif " OR " in condition.upper():
            parts = re.split(r'\s+OR\s+', condition, flags=re.IGNORECASE)
            return any(self._evaluate_where(row, part) for part in parts)
        
        # Handle comparisons
        operators = ["=", "!=", "<", ">", "<=", ">=", "LIKE", "IS NULL", "IS NOT NULL"]
        
        for op in operators:
            if f" {op} " in condition.upper():
                left, right = condition.split(f" {op} ", 1)
                left = left.strip()
                right = right.strip().strip("'")
                
                left_val = row.get(left, None)
                
                if op.upper() == "IS NULL":
                    return left_val is None
                elif op.upper() == "IS NOT NULL":
                    return left_val is not None
                elif op.upper() == "LIKE":
                    # Simple LIKE with % wildcard
                    pattern = right.replace("%", ".*")
                    return bool(re.match(pattern, str(left_val or "")))
                else:
                    # Convert right value
                    if right.isdigit():
                        right_val = int(right)
                    elif right.replace('.', '', 1).isdigit():
                        right_val = float(right)
                    elif right.upper() in ("TRUE", "FALSE"):
                        right_val = right.upper() == "TRUE"
                    elif right == "NULL":
                        right_val = None
                    else:
                        right_val = right
                    
                    # Compare
                    if op == "=":
                        return left_val == right_val
                    elif op == "!=":
                        return left_val != right_val
                    elif op == "<":
                        return left_val < right_val
                    elif op == ">":
                        return left_val > right_val
                    elif op == "<=":
                        return left_val <= right_val
                    elif op == ">=":
                        return left_val >= right_val
        
        return False
    
    def _execute_update(self, sql: str) -> List[Dict[str, Any]]:
        pattern = r"UPDATE (\w+) SET (.+?)(?: WHERE (.+))?$"
        match = re.match(pattern, sql, re.IGNORECASE)
        if not match:
            raise ValueError("Invalid UPDATE syntax")
        
        table_name = match.group(1)
        set_clause = match.group(2).strip()
        where_clause = match.group(3)
        
        if table_name not in self.tables:
            raise ValueError(f"Table '{table_name}' does not exist")
        
        table = self.tables[table_name]
        
        # Parse SET clause
        updates = {}
        for assignment in set_clause.split(","):
            col, value = assignment.split("=", 1)
            col = col.strip()
            value = value.strip().strip("'")
            
            # Parse value
            if value.isdigit():
                updates[col] = int(value)
            elif value.replace('.', '', 1).isdigit():
                updates[col] = float(value)
            elif value.upper() in ("TRUE", "FALSE"):
                updates[col] = value.upper() == "TRUE"
            elif value == "NULL":
                updates[col] = None
            else:
                updates[col] = value
        
        # Apply updates
        updated_count = 0
        for i, row in enumerate(table.rows):
            if not where_clause or self._evaluate_where(row, where_clause):
                # Validate updates
                for col, value in updates.items():
                    # Find column
                    col_obj = next((c for c in table.columns if c.name == col), None)
                    if not col_obj:
                        raise ValueError(f"Column '{col}' does not exist")
                    
                    if col_obj.is_unique and value is not None:
                        # Check for duplicates
                        for j, other_row in enumerate(table.rows):
                            if j != i and other_row.get(col) == value:
                                raise ValueError(f"Duplicate value for unique column '{col}'")
                
                # Apply updates
                row.update(updates)
                updated_count += 1
        
        if updated_count > 0:
            # Rebuild indexes
            for idx in table.indexes.values():
                self._rebuild_index(table_name, idx)
            self._save_table(table_name)
        
        return [{"status": f"{updated_count} row(s) updated"}]
    
    def _execute_delete(self, sql: str) -> List[Dict[str, Any]]:
        pattern = r"DELETE FROM (\w+)(?: WHERE (.+))?$"
        match = re.match(pattern, sql, re.IGNORECASE)
        if not match:
            raise ValueError("Invalid DELETE syntax")
        
        table_name = match.group(1)
        where_clause = match.group(2)
        
        if table_name not in self.tables:
            raise ValueError(f"Table '{table_name}' does not exist")
        
        table = self.tables[table_name]
        
        # Find rows to delete
        rows_to_delete = []
        for i, row in enumerate(table.rows):
            if not where_clause or self._evaluate_where(row, where_clause):
                rows_to_delete.append(i)
        
        # Delete rows (from end to beginning to preserve indices)
        deleted_count = 0
        for i in sorted(rows_to_delete, reverse=True):
            table.rows.pop(i)
            deleted_count += 1
        
        if deleted_count > 0:
            # Rebuild all indexes
            for idx in table.indexes.values():
                self._rebuild_index(table_name, idx)
            self._save_table(table_name)
        
        return [{"status": f"{deleted_count} row(s) deleted"}]
    
    def _execute_drop_table(self, sql: str) -> List[Dict[str, Any]]:
        pattern = r"DROP TABLE (\w+)"
        match = re.match(pattern, sql, re.IGNORECASE)
        if not match:
            raise ValueError("Invalid DROP TABLE syntax")
        
        table_name = match.group(1)
        
        if table_name not in self.tables:
            raise ValueError(f"Table '{table_name}' does not exist")
        
        del self.tables[table_name]
        
        # Remove data file
        data_file = os.path.join(self.data_dir, f"{table_name}.pkl")
        if os.path.exists(data_file):
            os.remove(data_file)
        
        return [{"status": f"Table '{table_name}' dropped successfully"}]
    
    def _execute_create_index(self, sql: str) -> List[Dict[str, Any]]:
        pattern = r"CREATE INDEX (\w+) ON (\w+) \((.+?)\)"
        match = re.match(pattern, sql, re.IGNORECASE)
        if not match:
            raise ValueError("Invalid CREATE INDEX syntax")
        
        index_name = match.group(1)
        table_name = match.group(2)
        columns_str = match.group(3)
        
        if table_name not in self.tables:
            raise ValueError(f"Table '{table_name}' does not exist")
        
        table = self.tables[table_name]
        column_names = [col.strip() for col in columns_str.split(",")]
        
        # Validate columns
        for col_name in column_names:
            if not any(col.name == col_name for col in table.columns):
                raise ValueError(f"Column '{col_name}' does not exist in table '{table_name}'")
        
        table.add_index(index_name, column_names)
        self._save_table(table_name)
        
        return [{"status": f"Index '{index_name}' created on '{table_name}'"}]
    
    def _rebuild_index(self, table_name: str, index: Index):
        table = self.tables[table_name]
        index.entries.clear()
        for i, row in enumerate(table.rows):
            key = tuple(row[col] for col in index.column_names if col in row)
            if key not in index.entries:
                index.entries[key] = []
            index.entries[key].append(i)
    
    def _begin_transaction(self):
        self._in_transaction = True
        self.transaction_log = []
    
    def _commit_transaction(self) -> List[str]:
        result = self.transaction_log.copy()
        self._in_transaction = False
        self.transaction_log = []
        return result
    
    def _rollback_transaction(self):
        self._in_transaction = False
        self.transaction_log = []
        # Reload tables from disk to undo changes
        self._load_tables()


class SQLREPL:
    def __init__(self, db: SimpleRDBMS):
        self.db = db
    
    def run(self):
        print("Simple RDBMS SQL REPL")
        print("Type 'EXIT' to quit, 'HELP' for help")
        print()
        
        while True:
            try:
                command = input("SQL> ").strip()
                
                if command.upper() == "EXIT":
                    break
                elif command.upper() == "HELP":
                    self._show_help()
                    continue
                elif not command:
                    continue
                elif command.upper() == "TABLES":
                    self._show_tables()
                    continue
                
                # Execute SQL
                results = self.db.execute_sql(command)
                
                # Display results
                if results:
                    if isinstance(results[0], dict) and "status" in results[0]:
                        print(results[0]["status"])
                    else:
                        # Display as table
                        if results:
                            headers = list(results[0].keys())
                            print(" | ".join(headers))
                            print("-" * (len(headers) * 10))
                            for row in results:
                                print(" | ".join(str(row.get(h, "")) for h in headers))
                            print(f"\n{len(results)} row(s) returned")
                
            except Exception as e:
                print(f"Error: {e}")
    
    def _show_help(self):
        help_text = """
        Available SQL Commands:
        - CREATE TABLE table_name (col1 TYPE, col2 TYPE, ...)
        - INSERT INTO table_name VALUES (val1, val2, ...)
        - SELECT * FROM table_name [WHERE condition]
        - UPDATE table_name SET col=val [WHERE condition]
        - DELETE FROM table_name [WHERE condition]
        - DROP TABLE table_name
        - CREATE INDEX idx_name ON table_name (col1, col2)
        - BEGIN TRANSACTION
        - COMMIT
        - ROLLBACK
        
        Data Types: INTEGER, TEXT, REAL, BOOLEAN
        Constraints: PRIMARY KEY, UNIQUE, NOT NULL
        
        REPL Commands:
        - TABLES: List all tables
        - HELP: Show this help
        - EXIT: Quit REPL
        """
        print(help_text)
    
    def _show_tables(self):
        if not self.db.tables:
            print("No tables in database")
            return
        
        print("\nTables in database:")
        for table_name, table in self.db.tables.items():
            print(f"\n{table_name}:")
            for col in table.columns:
                constraints = []
                if col.is_primary:
                    constraints.append("PRIMARY KEY")
                if col.is_unique:
                    constraints.append("UNIQUE")
                if not col.is_nullable:
                    constraints.append("NOT NULL")
                
                constraint_str = f" [{', '.join(constraints)}]" if constraints else ""
                print(f"  - {col.name}: {col.data_type.value}{constraint_str}")
            print(f"  Rows: {len(table.rows)}")
            print(f"  Indexes: {len(table.indexes)}")


# Web Application using our RDBMS
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

class WebRDBMS:
    def __init__(self, db: SimpleRDBMS):
        self.db = db
    
    def handle_request(self, path: str, method: str, data: Dict) -> Tuple[int, Dict]:
        if path == "/api/tables" and method == "GET":
            tables = []
            for name, table in self.db.tables.items():
                tables.append({
                    "name": name,
                    "columns": len(table.columns),
                    "rows": len(table.rows)
                })
            return 200, {"tables": tables}
        
        elif path == "/api/query" and method == "POST":
            sql = data.get("sql", "")
            if not sql:
                return 400, {"error": "SQL query required"}
            
            try:
                results = self.db.execute_sql(sql)
                return 200, {"results": results}
            except Exception as e:
                return 400, {"error": str(e)}
        
        elif path.startswith("/api/table/") and method == "GET":
            table_name = path.split("/")[-1]
            if table_name not in self.db.tables:
                return 404, {"error": f"Table '{table_name}' not found"}
            
            try:
                results = self.db.execute_sql(f"SELECT * FROM {table_name}")
                return 200, {
                    "table": table_name,
                    "columns": [col.name for col in self.db.tables[table_name].columns],
                    "rows": results
                }
            except Exception as e:
                return 400, {"error": str(e)}
        
        else:
            return 404, {"error": "Not found"}


class WebHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, web_db=None, **kwargs):
        self.web_db = web_db
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        if self.path == "/":
            self._serve_file("index.html")
        elif self.path == "/style.css":
            self._serve_file("style.css")
        else:
            status, data = self.web_db.handle_request(self.path, "GET", {})
            self._send_json_response(status, data)
    
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        data = json.loads(post_data) if post_data else {}
        
        status, response_data = self.web_db.handle_request(self.path, "POST", data)
        self._send_json_response(status, response_data)
    
    def _serve_file(self, filename):
        try:
            with open(filename, 'rb') as f:
                content = f.read()
            
            if filename.endswith('.html'):
                content_type = 'text/html'
            elif filename.endswith('.css'):
                content_type = 'text/css'
            else:
                content_type = 'text/plain'
            
            self.send_response(200)
            self.send_header('Content-type', content_type)
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"File not found")
    
    def _send_json_response(self, status, data):
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))


def create_web_files():
    # Create HTML file
    html_content = """<!DOCTYPE html>
<html>
<head>
    <title>Simple RDBMS Web Interface</title>
    <link rel="stylesheet" href="/style.css">
</head>
<body>
    <div class="container">
        <h1> Simple RDBMS Web Interface</h1>
        
        <div class="section">
            <h2> Database Tables</h2>
            <div id="tables-list"></div>
            <button onclick="loadTables()">Refresh Tables</button>
        </div>
        
        <div class="section">
            <h2>⚡ SQL Query</h2>
            <textarea id="sql-query" placeholder="Enter SQL query here...">SELECT * FROM users</textarea>
            <button onclick="executeQuery()">Execute Query</button>
            <div id="query-results"></div>
        </div>
        
        <div class="section">
            <h2> Example Queries</h2>
            <div class="examples">
                <button onclick="setQuery('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE, age INTEGER)')">Create Users Table</button>
                <button onclick="setQuery(\"INSERT INTO users VALUES (1, 'Alice', 'alice@example.com', 25)\")">Insert Sample Data</button>
                <button onclick="setQuery('SELECT * FROM users')">Select All Users</button>
                <button onclick="setQuery('UPDATE users SET age = 26 WHERE name = \\'Alice\\'')">Update User</button>
                <button onclick="setQuery('CREATE INDEX idx_email ON users (email)')">Create Email Index</button>
            </div>
        </div>
    </div>
    
    <script>
    async function loadTables() {
        const response = await fetch('/api/tables');
        const data = await response.json();
        
        const tablesDiv = document.getElementById('tables-list');
        tablesDiv.innerHTML = '';
        
        if (data.tables && data.tables.length > 0) {
            const table = document.createElement('table');
            table.innerHTML = `
                <tr>
                    <th>Table Name</th>
                    <th>Columns</th>
                    <th>Rows</th>
                    <th>Actions</th>
                </tr>
            `;
            
            data.tables.forEach(t => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${t.name}</td>
                    <td>${t.columns}</td>
                    <td>${t.rows}</td>
                    <td><button onclick="viewTable('${t.name}')">View</button></td>
                `;
                table.appendChild(row);
            });
            
            tablesDiv.appendChild(table);
        } else {
            tablesDiv.innerHTML = '<p>No tables in database</p>';
        }
    }
    
    async function executeQuery() {
        const query = document.getElementById('sql-query').value;
        const response = await fetch('/api/query', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({sql: query})
        });
        
        const data = await response.json();
        const resultsDiv = document.getElementById('query-results');
        
        if (response.ok) {
            if (data.results && data.results.length > 0) {
                const table = document.createElement('table');
                
                // Create headers
                const headers = Object.keys(data.results[0]);
                const headerRow = document.createElement('tr');
                headers.forEach(h => {
                    const th = document.createElement('th');
                    th.textContent = h;
                    headerRow.appendChild(th);
                });
                table.appendChild(headerRow);
                
                // Create data rows
                data.results.forEach(row => {
                    const dataRow = document.createElement('tr');
                    headers.forEach(h => {
                        const td = document.createElement('td');
                        td.textContent = row[h] !== undefined ? row[h] : '';
                        dataRow.appendChild(td);
                    });
                    table.appendChild(dataRow);
                });
                
                resultsDiv.innerHTML = '';
                resultsDiv.appendChild(table);
                
                // Also refresh tables list
                loadTables();
            } else {
                resultsDiv.innerHTML = `<p>Query executed successfully: ${data.results?.[0]?.status || 'No results'}</p>`;
            }
        } else {
            resultsDiv.innerHTML = `<p class="error">Error: ${data.error}</p>`;
        }
    }
    
    function setQuery(sql) {
        document.getElementById('sql-query').value = sql;
    }
    
    async function viewTable(tableName) {
        setQuery(`SELECT * FROM ${tableName}`);
        await executeQuery();
    }
    
    // Load tables on page load
    loadTables();
    </script>
</body>
</html>"""
    
    with open("index.html", "w") as f:
        f.write(html_content)
    
    # Create CSS file
    css_content = """body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
    margin: 0;
    padding: 20px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh;
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    background: white;
    padding: 30px;
    border-radius: 15px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
}

h1 {
    color: #333;
    text-align: center;
    margin-bottom: 40px;
}

.section {
    background: #f8f9fa;
    padding: 25px;
    border-radius: 10px;
    margin-bottom: 30px;
    border-left: 5px solid #667eea;
}

h2 {
    color: #444;
    margin-top: 0;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 10px;
}

#sql-query {
    width: 100%;
    height: 100px;
    padding: 15px;
    border: 2px solid #ddd;
    border-radius: 8px;
    font-family: 'Courier New', monospace;
    font-size: 14px;
    resize: vertical;
    margin-bottom: 15px;
}

button {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border: none;
    padding: 12px 24px;
    border-radius: 8px;
    cursor: pointer;
    font-weight: 600;
    transition: transform 0.2s, box-shadow 0.2s;
    margin-right: 10px;
    margin-bottom: 10px;
}

button:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 20px rgba(102, 126, 234, 0.4);
}

.examples {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
}

.examples button {
    background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
    font-size: 12px;
    padding: 8px 16px;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin: 20px 0;
    background: white;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
}

th {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 15px;
    text-align: left;
    font-weight: 600;
}

td {
    padding: 12px 15px;
    border-bottom: 1px solid #eee;
}

tr:hover td {
    background-color: #f5f7ff;
}

#query-results {
    margin-top: 20px;
    overflow-x: auto;
}

.error {
    color: #e74c3c;
    background: #ffeaea;
    padding: 15px;
    border-radius: 8px;
    margin-top: 15px;
}
"""
    
    with open("style.css", "w") as f:
        f.write(css_content)


def main():
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--web":
        # Start web server
        print("Starting Simple RDBMS Web Interface...")
        print("Server running at http://localhost:8080")
        
        create_web_files()
        
        db = SimpleRDBMS()
        web_db = WebRDBMS(db)
        
        # Initialize with sample data
        try:
            db.execute_sql("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE,
                    age INTEGER
                )
            """)
            
            db.execute_sql("""
                INSERT INTO users VALUES 
                (1, 'Alice Johnson', 'alice@example.com', 28),
                (2, 'Bob Smith', 'bob@example.com', 32),
                (3, 'Charlie Brown', 'charlie@example.com', 25)
            """)
        except:
            pass
        
        server = HTTPServer(('localhost', 8080), 
                           lambda *args, **kwargs: WebHandler(*args, web_db=web_db, **kwargs))
        server.serve_forever()
    
    else:
        # Start REPL
        print("Simple RDBMS - Interactive SQL REPL")
        print("===================================")
        print("Type '--web' as argument to start web interface\n")
        
        db = SimpleRDBMS()
        repl = SQLREPL(db)
        repl.run()


if __name__ == "__main__":
    main()