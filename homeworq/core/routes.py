import uuid
from asyncio import sleep
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException, WebSocket
from fastapi.responses import HTMLResponse

router = APIRouter()

# In-memory store for tasks and running task instances (for demonstration purposes)
tasks_registry: Dict[str, Any] = {}
running_tasks: Dict[str, Any] = {}

# HTML for WebSocket demo
html = """
<!DOCTYPE html>
<html>
    <head>
        <title>WebSocket Task Updates</title>
    </head>
    <body>
        <h1>WebSocket Task Updates</h1>
        <ul id="messages"></ul>
        <script>
            const ws = new WebSocket("ws://localhost:8000/ws");
            ws.onmessage = function(event) {
                const messages = document.getElementById("messages");
                const message = document.createElement("li");
                const content = document.createTextNode(event.data);
                message.appendChild(content);
                messages.appendChild(message);
            };
        </script>
    </body>
</html>
"""

@router.get("/")
async def get():
    """Serve a simple HTML page to test WebSocket."""
    return HTMLResponse(html)


# Task endpoints
@router.post("/tasks/")
async def create_task(name: str, interval: int, background_tasks: BackgroundTasks):
    """Create a new task."""
    task_id = str(uuid.uuid4())
    
    async def task_runner():
        while task_id in running_tasks:
            # Simulate a recurring task
            print(f"Running task: {name}")
            await sleep(interval)

    task_data = {"id": task_id, "name": name, "interval": interval}
    tasks_registry[task_id] = task_data
    background_tasks.add_task(task_runner)
    running_tasks[task_id] = True
    
    return {"message": "Task created", "task_id": task_id}


@router.get("/tasks/")
async def list_tasks():
    """List all registered tasks."""
    return {"tasks": list(tasks_registry.values())}


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """Delete a task and stop it from running."""
    if task_id not in tasks_registry:
        raise HTTPException(status_code=404, detail="Task not found")
    del tasks_registry[task_id]
    running_tasks.pop(task_id, None)
    return {"message": "Task deleted"}


# WebSocket for real-time updates
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        for task in tasks_registry.values():
            await websocket.send_text(f"Task running: {task['name']} (interval: {task['interval']}s)")
        await sleep(5)