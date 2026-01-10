from rdbms import SimpleRDBMS, SQLREPL
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

class TodoApp:
    def __init__(self):
        self.db = SimpleRDBMS(data_dir="todo_data")
        self._init_database()
    
    def _init_database(self):
        # Create todos table if it doesn't exist
        try:
            self.db.execute_sql("""
                CREATE TABLE todos (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    completed BOOLEAN DEFAULT FALSE,
                    created_at TEXT,
                    priority INTEGER DEFAULT 3
                )
            """)
        except:
            pass  # Table already exists
    
    def get_all_todos(self):
        results = self.db.execute_sql("""
            SELECT * FROM todos 
            ORDER BY 
                CASE WHEN completed THEN 1 ELSE 0 END,
                priority,
                created_at DESC
        """)
        return results
    
    def add_todo(self, title, description="", priority=3):
        import time
        created_at = time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Get next ID
        todos = self.get_all_todos()
        next_id = max([t['id'] for t in todos], default=0) + 1
        
        self.db.execute_sql(f"""
            INSERT INTO todos (id, title, description, completed, created_at, priority)
            VALUES ({next_id}, '{title}', '{description}', FALSE, '{created_at}', {priority})
        """)
        
        return self.get_todo(next_id)
    
    def get_todo(self, todo_id):
        results = self.db.execute_sql(f"SELECT * FROM todos WHERE id = {todo_id}")
        return results[0] if results else None
    
    def update_todo(self, todo_id, **updates):
        if not updates:
            return None
        
        set_clause = ", ".join([f"{k} = '{v}'" if isinstance(v, str) else f"{k} = {v}" 
                               for k, v in updates.items()])
        
        self.db.execute_sql(f"""
            UPDATE todos 
            SET {set_clause}
            WHERE id = {todo_id}
        """)
        
        return self.get_todo(todo_id)
    
    def delete_todo(self, todo_id):
        self.db.execute_sql(f"DELETE FROM todos WHERE id = {todo_id}")
        return True
    
    def toggle_todo(self, todo_id):
        todo = self.get_todo(todo_id)
        if todo:
            new_status = not todo['completed']
            return self.update_todo(todo_id, completed=new_status)
        return None


class TodoHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, todo_app=None, **kwargs):
        self.todo_app = todo_app
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        if self.path == "/":
            self._serve_home()
        elif self.path == "/api/todos":
            self._send_json(200, self.todo_app.get_all_todos())
        else:
            self._send_json(404, {"error": "Not found"})
    
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        data = json.loads(post_data) if post_data else {}
        
        if self.path == "/api/todos":
            title = data.get('title', '').strip()
            if not title:
                self._send_json(400, {"error": "Title is required"})
                return
            
            description = data.get('description', '')
            priority = min(max(int(data.get('priority', 3)), 1), 5)  # 1-5 priority
            
            todo = self.todo_app.add_todo(title, description, priority)
            self._send_json(201, todo)
        
        elif self.path.startswith("/api/todos/"):
            parts = self.path.split("/")
            if len(parts) >= 4:
                todo_id = int(parts[3])
                action = parts[4] if len(parts) > 4 else ""
                
                if action == "toggle":
                    todo = self.todo_app.toggle_todo(todo_id)
                    if todo:
                        self._send_json(200, todo)
                    else:
                        self._send_json(404, {"error": "Todo not found"})
                elif action == "delete":
                    success = self.todo_app.delete_todo(todo_id)
                    self._send_json(200, {"success": success})
                else:
                    # Update todo
                    todo = self.todo_app.update_todo(todo_id, **data)
                    if todo:
                        self._send_json(200, todo)
                    else:
                        self._send_json(404, {"error": "Todo not found"})
            else:
                self._send_json(404, {"error": "Invalid path"})
        
        else:
            self._send_json(404, {"error": "Not found"})
    
    def _serve_home(self):
        html = """<!DOCTYPE html>
<html>
<head>
    <title>Simple Todo App</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 30px 80px rgba(0,0,0,0.3);
        }
        h1 { 
            color: #333; 
            margin-bottom: 30px;
            text-align: center;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 15px;
        }
        h1 span { color: #667eea; }
        .todo-form {
            background: #f8f9fa;
            padding: 25px;
            border-radius: 15px;
            margin-bottom: 30px;
            border: 2px dashed #ddd;
        }
        .form-group { margin-bottom: 15px; }
        label { 
            display: block; 
            margin-bottom: 5px; 
            font-weight: 600;
            color: #555;
        }
        input, textarea, select {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        input:focus, textarea:focus, select:focus {
            outline: none;
            border-color: #667eea;
        }
        button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 14px 28px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 25px rgba(102, 126, 234, 0.4);
        }
        .todo-list {
            margin-top: 30px;
        }
        .todo-item {
            background: white;
            padding: 20px;
            margin-bottom: 15px;
            border-radius: 12px;
            border-left: 5px solid;
            box-shadow: 0 5px 15px rgba(0,0,0,0.08);
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: all 0.3s;
        }
        .todo-item:hover {
            transform: translateX(5px);
            box-shadow: 0 10px 25px rgba(0,0,0,0.12);
        }
        .todo-item.completed {
            opacity: 0.7;
            border-left-color: #4CAF50;
        }
        .todo-item.high { border-left-color: #ff4757; }
        .todo-item.medium { border-left-color: #ffa502; }
        .todo-item.low { border-left-color: #2ed573; }
        .todo-info { flex-grow: 1; }
        .todo-title { 
            font-size: 18px; 
            font-weight: 600;
            margin-bottom: 5px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .todo-title input[type="checkbox"] {
            width: 20px;
            height: 20px;
        }
        .todo-desc {
            color: #666;
            margin-bottom: 10px;
        }
        .todo-meta {
            font-size: 12px;
            color: #888;
            display: flex;
            gap: 15px;
        }
        .todo-actions {
            display: flex;
            gap: 10px;
        }
        .todo-actions button {
            padding: 8px 16px;
            font-size: 14px;
            border-radius: 6px;
        }
        .priority-badge {
            padding: 3px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            color: white;
        }
        .priority-1 { background: #ff4757; }
        .priority-2 { background: #ff6348; }
        .priority-3 { background: #ffa502; }
        .priority-4 { background: #2ed573; }
        .priority-5 { background: #1e90ff; }
        .empty-state {
            text-align: center;
            padding: 50px;
            color: #888;
            font-style: italic;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>✅ <span>Simple Todo App</span> using Custom RDBMS</h1>
        
        <div class="todo-form">
            <h3>Add New Todo</h3>
            <div class="form-group">
                <label>Title *</label>
                <input type="text" id="todo-title" placeholder="What needs to be done?">
            </div>
            <div class="form-group">
                <label>Description</label>
                <textarea id="todo-desc" rows="3" placeholder="Additional details..."></textarea>
            </div>
            <div class="form-group">
                <label>Priority</label>
                <select id="todo-priority">
                    <option value="3">Medium</option>
                    <option value="1">High</option>
                    <option value="2">High-Medium</option>
                    <option value="4">Low-Medium</option>
                    <option value="5">Low</option>
                </select>
            </div>
            <button onclick="addTodo()">Add Todo</button>
        </div>
        
        <div class="todo-list" id="todo-list">
            <!-- Todos will be loaded here -->
        </div>
    </div>
    
    <script>
    async function loadTodos() {
        const response = await fetch('/api/todos');
        const todos = await response.json();
        
        const container = document.getElementById('todo-list');
        
        if (todos.length === 0) {
            container.innerHTML = '<div class="empty-state">No todos yet. Add one above!</div>';
            return;
        }
        
        container.innerHTML = '';
        
        todos.forEach(todo => {
            const priorityClass = `priority-${todo.priority || 3}`;
            const completedClass = todo.completed ? 'completed' : '';
            const priorityText = ['High', 'High-Medium', 'Medium', 'Low-Medium', 'Low'][(todo.priority || 3) - 1];
            
            const todoEl = document.createElement('div');
            todoEl.className = `todo-item ${completedClass} ${priorityText.toLowerCase().replace('-', ' ')}`;
            todoEl.innerHTML = `
                <div class="todo-info">
                    <div class="todo-title">
                        <input type="checkbox" ${todo.completed ? 'checked' : ''} 
                               onclick="toggleTodo(${todo.id})">
                        ${todo.title}
                    </div>
                    ${todo.description ? `<div class="todo-desc">${todo.description}</div>` : ''}
                    <div class="todo-meta">
                        <span>Created: ${todo.created_at || 'N/A'}</span>
                        <span class="priority-badge ${priorityClass}">${priorityText} Priority</span>
                    </div>
                </div>
                <div class="todo-actions">
                    ${todo.completed ? '' : '<button onclick="editTodo(' + todo.id + ')">Edit</button>'}
                    <button onclick="deleteTodo(${todo.id})" style="background: #ff4757;">Delete</button>
                </div>
            `;
            container.appendChild(todoEl);
        });
    }
    
    async function addTodo() {
        const title = document.getElementById('todo-title').value.trim();
        const description = document.getElementById('todo-desc').value.trim();
        const priority = parseInt(document.getElementById('todo-priority').value);
        
        if (!title) {
            alert('Please enter a title');
            return;
        }
        
        const response = await fetch('/api/todos', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({title, description, priority})
        });
        
        if (response.ok) {
            document.getElementById('todo-title').value = '';
            document.getElementById('todo-desc').value = '';
            loadTodos();
        }
    }
    
    async function toggleTodo(todoId) {
        const response = await fetch(`/api/todos/${todoId}/toggle`, {method: 'POST'});
        if (response.ok) {
            loadTodos();
        }
    }
    
    async function editTodo(todoId) {
        const newTitle = prompt('Enter new title:');
        if (newTitle) {
            const response = await fetch(`/api/todos/${todoId}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({title: newTitle})
            });
            if (response.ok) {
                loadTodos();
            }
        }
    }
    
    async function deleteTodo(todoId) {
        if (confirm('Are you sure you want to delete this todo?')) {
            const response = await fetch(`/api/todos/${todoId}/delete`, {method: 'POST'});
            if (response.ok) {
                loadTodos();
            }
        }
    }
    
    // Load todos on page load
    loadTodos();
    
    // Add Enter key support
    document.getElementById('todo-title').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') addTodo();
    });
    </script>
</body>
</html>"""
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def _send_json(self, status, data):
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))


def run_todo_app():
    print("Starting Todo App with Simple RDBMS...")
    print("Web interface available at http://localhost:8000")
    print()
    print("The app demonstrates:")
    print("1. CREATE TABLE - Creating todos table")
    print("2. INSERT - Adding new todos")
    print("3. SELECT - Loading todos with sorting")
    print("4. UPDATE - Toggling completion status")
    print("5. DELETE - Removing todos")
    print()
    print("All data is stored using our custom RDBMS!")
    
    todo_app = TodoApp()
    
    # Add some sample todos
    todo_app.add_todo("Learn about RDBMS", "Study how relational databases work", 1)
    todo_app.add_todo("Build a simple database", "Implement basic SQL features", 2)
    todo_app.add_todo("Create a web interface", "Build a frontend for the database", 3)
    
    server = HTTPServer(('localhost', 8000), 
                       lambda *args, **kwargs: TodoHandler(*args, todo_app=todo_app, **kwargs))
    server.serve_forever()


if __name__ == "__main__":
    run_todo_app()