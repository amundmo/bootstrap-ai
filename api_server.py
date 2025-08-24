#!/usr/bin/env python3
"""
FastAPI backend server for Claude Code Automation UI
Provides REST API and WebSocket endpoints for task management and real-time updates
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from fastapi import FastAPI, WebSocket, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from claude_automation import ClaudeCodeAutomation

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Claude Code Automation API", version="1.0.0")

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class TaskCreate(BaseModel):
    title: str
    description: str
    requirements: List[str] = []
    acceptance_criteria: List[str] = []
    priority: str = "medium"

class TaskUpdate(BaseModel):
    status: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None

class ChatMessage(BaseModel):
    content: str
    context: Optional[str] = None

class TaskCreationRequest(BaseModel):
    message: str
    context: Optional[str] = None

# In-memory storage (replace with database in production)
tasks: Dict[str, Dict] = {}
chat_messages: List[Dict] = []
automation_status = {
    "running": False,
    "current_task": None,
    "loop_count": 0,
    "last_cycle_duration": None,
    "error_count": 0
}

# WebSocket connections
websocket_connections: List[WebSocket] = []

# Automation instance
automation_instance: Optional[ClaudeCodeAutomation] = None
automation_task: Optional[asyncio.Task] = None

async def broadcast_message(message: Dict):
    """Broadcast message to all connected WebSocket clients"""
    if websocket_connections:
        disconnected = []
        for websocket in websocket_connections:
            try:
                await websocket.send_text(json.dumps(message))
            except:
                disconnected.append(websocket)
        
        # Remove disconnected websockets
        for ws in disconnected:
            websocket_connections.remove(ws)

def create_task(task_data: Dict) -> Dict:
    """Create a new task"""
    task_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    
    task = {
        "id": task_id,
        "title": task_data["title"],
        "description": task_data["description"],
        "requirements": task_data.get("requirements", []),
        "acceptance_criteria": task_data.get("acceptance_criteria", []),
        "priority": task_data.get("priority", "medium"),
        "status": "pending",
        "created_at": now,
        "updated_at": now
    }
    
    tasks[task_id] = task
    return task

async def simulate_llm_task_creation(message: str) -> Dict:
    """Simulate LLM-powered task creation from user message"""
    # In a real implementation, this would call an LLM API
    # For now, we'll parse the message and create a structured task
    
    await asyncio.sleep(1)  # Simulate API call delay
    
    # Simple keyword-based task creation
    title = f"Automated Task: {message[:50]}..."
    description = f"Task created from user request: {message}"
    
    requirements = []
    acceptance_criteria = []
    priority = "medium"
    
    # Basic keyword detection for requirements
    if "api" in message.lower():
        requirements.extend([
            "Create REST API endpoints",
            "Add proper error handling",
            "Include API documentation"
        ])
        acceptance_criteria.extend([
            "API endpoints respond correctly",
            "Error responses are properly formatted",
            "API documentation is complete"
        ])
    
    if "test" in message.lower():
        requirements.extend([
            "Write unit tests",
            "Add integration tests",
            "Ensure test coverage > 80%"
        ])
        acceptance_criteria.extend([
            "All tests pass",
            "Test coverage meets requirements"
        ])
    
    if "database" in message.lower() or "db" in message.lower():
        requirements.extend([
            "Design database schema",
            "Create migrations",
            "Add database connection handling"
        ])
    
    # Determine priority based on keywords
    if any(word in message.lower() for word in ["urgent", "critical", "asap", "immediately"]):
        priority = "critical"
    elif any(word in message.lower() for word in ["important", "high", "priority"]):
        priority = "high"
    elif any(word in message.lower() for word in ["low", "minor", "later"]):
        priority = "low"
    
    return {
        "title": title,
        "description": description,
        "requirements": requirements,
        "acceptance_criteria": acceptance_criteria,
        "priority": priority
    }

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    websocket_connections.append(websocket)
    
    try:
        # Send current status
        await websocket.send_text(json.dumps({
            "type": "status_update",
            "data": automation_status
        }))
        
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle different message types
            if message["type"] == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if websocket in websocket_connections:
            websocket_connections.remove(websocket)

# API Routes
@app.get("/api/tasks")
async def get_tasks():
    """Get all tasks"""
    return {"tasks": list(tasks.values())}

@app.post("/api/tasks")
async def create_task_endpoint(task_data: TaskCreate):
    """Create a new task"""
    task = create_task(task_data.dict())
    
    # Broadcast to WebSocket clients
    await broadcast_message({
        "type": "task_created",
        "data": task
    })
    
    return {"task": task}

@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    """Get a specific task"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": tasks[task_id]}

@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: str, task_update: TaskUpdate):
    """Update a task"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = tasks[task_id]
    update_data = task_update.dict(exclude_unset=True)
    
    for field, value in update_data.items():
        task[field] = value
    
    task["updated_at"] = datetime.now().isoformat()
    
    # Broadcast to WebSocket clients
    await broadcast_message({
        "type": "task_updated",
        "data": task
    })
    
    return {"task": task}

@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    """Delete a task"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    deleted_task = tasks.pop(task_id)
    
    # Broadcast to WebSocket clients
    await broadcast_message({
        "type": "task_deleted",
        "data": {"task_id": task_id}
    })
    
    return {"message": "Task deleted successfully"}

@app.post("/api/chat/create-task")
async def chat_create_task(request: TaskCreationRequest):
    """Create a task from chat message using LLM"""
    try:
        # Add user message to chat history
        user_message = {
            "id": str(uuid.uuid4()),
            "type": "user",
            "content": request.message,
            "timestamp": datetime.now().isoformat()
        }
        chat_messages.append(user_message)
        
        # Broadcast user message
        await broadcast_message({
            "type": "chat_message",
            "data": user_message
        })
        
        # Generate task using LLM simulation
        task_data = await simulate_llm_task_creation(request.message)
        task = create_task(task_data)
        
        # Create assistant response
        assistant_message = {
            "id": str(uuid.uuid4()),
            "type": "assistant",
            "content": f"I've created a new task: '{task['title']}'\n\nThis task includes {len(task['requirements'])} requirements and {len(task['acceptance_criteria'])} acceptance criteria. The task has been added to your automation queue with {task['priority']} priority.",
            "timestamp": datetime.now().isoformat(),
            "task_id": task["id"]
        }
        chat_messages.append(assistant_message)
        
        # Broadcast assistant message and task creation
        await broadcast_message({
            "type": "chat_message",
            "data": assistant_message
        })
        
        await broadcast_message({
            "type": "task_created",
            "data": task
        })
        
        return {
            "task": task,
            "message": assistant_message,
            "explanation": "Task created successfully from your message"
        }
    
    except Exception as e:
        logger.error(f"Error creating task from chat: {e}")
        error_message = {
            "id": str(uuid.uuid4()),
            "type": "system",
            "content": f"Sorry, I encountered an error while creating the task: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }
        chat_messages.append(error_message)
        
        await broadcast_message({
            "type": "chat_message",
            "data": error_message
        })
        
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chat/messages")
async def get_chat_messages():
    """Get chat message history"""
    return {"messages": chat_messages}

@app.get("/api/status")
async def get_automation_status():
    """Get automation system status"""
    return {"status": automation_status}

async def run_automation_loop():
    """Background task to run automation loop"""
    global automation_status, automation_instance
    
    try:
        automation_instance = ClaudeCodeAutomation("/home/john/dev/personal/bootstrap")
        
        while automation_status["running"]:
            automation_status["loop_count"] += 1
            
            # Broadcast status update
            await broadcast_message({
                "type": "status_update",
                "data": automation_status
            })
            
            try:
                # Run one automation cycle
                result = await automation_instance.run_complete_cycle()
                
                automation_status["last_cycle_duration"] = result.get("duration")
                
                if result["status"] == "error":
                    automation_status["error_count"] += 1
                    
                    # Broadcast error
                    await broadcast_message({
                        "type": "automation_error",
                        "data": {
                            "error": result.get("error_details", {}).get("error"),
                            "loop_count": automation_status["loop_count"]
                        }
                    })
                
            except Exception as e:
                logger.error(f"Error in automation loop: {e}")
                automation_status["error_count"] += 1
            
            # Wait before next cycle
            await asyncio.sleep(10)
    
    except Exception as e:
        logger.error(f"Automation loop failed: {e}")
        automation_status["running"] = False

@app.post("/api/automation/start")
async def start_automation(background_tasks: BackgroundTasks):
    """Start the automation system"""
    global automation_task, automation_status
    
    if automation_status["running"]:
        return {"message": "Automation is already running"}
    
    automation_status["running"] = True
    automation_status["error_count"] = 0
    
    # Start background task
    automation_task = asyncio.create_task(run_automation_loop())
    
    await broadcast_message({
        "type": "automation_started",
        "data": automation_status
    })
    
    return {"message": "Automation started successfully"}

@app.post("/api/automation/stop")
async def stop_automation():
    """Stop the automation system"""
    global automation_task, automation_status
    
    if not automation_status["running"]:
        return {"message": "Automation is not running"}
    
    automation_status["running"] = False
    
    if automation_task:
        automation_task.cancel()
        try:
            await automation_task
        except asyncio.CancelledError:
            pass
    
    await broadcast_message({
        "type": "automation_stopped",
        "data": automation_status
    })
    
    return {"message": "Automation stopped successfully"}

# Serve React build files (in production)
if Path("build").exists():
    app.mount("/", StaticFiles(directory="build", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8009,
        reload=True,
        log_level="info"
    )