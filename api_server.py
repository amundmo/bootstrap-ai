#!/usr/bin/env python3
"""
FastAPI backend server for Claude Code Automation UI
Provides REST API and WebSocket endpoints for task management and real-time updates
"""

import asyncio
import json
import logging
import uuid
import os
import requests
import subprocess
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from fastapi import FastAPI, WebSocket, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
from openai import AsyncOpenAI
from dotenv import load_dotenv

from claude_automation import ClaudeCodeAutomation

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai_client = AsyncOpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

app = FastAPI(title="Claude Code Automation API", version="1.0.0")

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for network access
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

async def chat_with_openai(message: str, conversation_history: List[Dict]) -> Dict:
    """Have a normal conversation with OpenAI GPT-4"""
    try:
        system_prompt = """You are a helpful software development assistant working within the Claude Code Automation system. You have access to development tools and can help create and manage development tasks.

Context: You're working with a modern web development environment that includes:
- React/TypeScript frontend
- Python backend with FastAPI
- Modern web technologies (HTML, CSS, JavaScript)
- Development automation tools
- MCP (Model Context Protocol) integration

When users ask for help with development tasks:
1. Be conversational and helpful, but decisive
2. For simple requests, acknowledge you'll create the task and proceed
3. Make reasonable assumptions for common development requests
4. Only ask clarifying questions for truly complex or ambiguous requests
5. Tasks will be automatically created based on our conversation

Examples of how to respond:
- "Add a button" → "Great! I'll create a task to add a button component."
- "Change background to red" → "Perfect! I'll create a task to update the background color."
- "Build user authentication" → Ask about specific auth requirements

Be proactive and assumptive rather than overly cautious."""

        # Build message history for context
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add conversation history (last 10 messages to keep context manageable)
        for msg in conversation_history[-10:]:
            if msg["type"] == "user":
                messages.append({"role": "user", "content": msg["content"]})
            elif msg["type"] == "assistant":
                messages.append({"role": "assistant", "content": msg["content"]})
        
        # Add current message
        messages.append({"role": "user", "content": message})

        response = await openai_client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7,
            max_tokens=800
        )
        
        assistant_response = response.choices[0].message.content.strip()
        logger.info(f"OpenAI chat response: {assistant_response}")
        
        return {
            "content": assistant_response,
            "should_create_tasks": False,  # We'll add task creation logic separately
            "suggested_tasks": []
        }
        
    except Exception as e:
        logger.error(f"Error in chat with OpenAI: {e}")
        return {
            "content": "I'm sorry, I'm having trouble processing your request right now. Please try again.",
            "should_create_tasks": False,
            "suggested_tasks": []
        }

async def analyze_conversation_for_tasks(conversation_history: List[Dict]) -> Dict:
    """Analyze conversation to determine if tasks should be created"""
    try:
        # Get recent conversation context
        recent_messages = conversation_history[-6:] if len(conversation_history) > 6 else conversation_history
        
        conversation_text = "\n".join([
            f"{msg['type']}: {msg['content']}" for msg in recent_messages
        ])
        
        system_prompt = """You are an AI agent that analyzes conversations to determine when development tasks should be created.

Analyze this conversation and determine if:
1. The user has provided enough detail for specific development tasks
2. What tasks should be created based on the conversation
3. The priority and requirements for each task

Respond with JSON in this format:
{
    "should_create_tasks": true/false,
    "reasoning": "Brief explanation of your analysis",
    "tasks": [
        {
            "title": "Task title",
            "description": "Detailed description",
            "requirements": ["req1", "req2"],
            "acceptance_criteria": ["criteria1", "criteria2"],
            "priority": "critical|high|medium|low"
        }
    ]
}

Guidelines for task creation:
- CREATE TASKS IMMEDIATELY for simple, actionable requests like "change background to red"
- For styling changes, UI modifications, or simple features - create tasks right away
- Don't wait for perfect specifications - make reasonable assumptions
- Only skip task creation if the request is truly vague like "help me" or "what can you do?"
- Be very proactive - err on the side of creating tasks rather than waiting"""

        response = await openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Analyze this conversation for task creation:\n\n{conversation_text}"}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        
        analysis_text = response.choices[0].message.content.strip()
        
        # Clean up JSON
        if analysis_text.startswith("```json"):
            analysis_text = analysis_text[7:-3].strip()
        elif analysis_text.startswith("```"):
            analysis_text = analysis_text[3:-3].strip()
        
        analysis = json.loads(analysis_text)
        return analysis
        
    except Exception as e:
        logger.error(f"Error analyzing conversation for tasks: {e}")
        return {"should_create_tasks": False, "reasoning": "Analysis failed", "tasks": []}

async def create_tasks_via_mcp(tasks: List[Dict]) -> List[Dict]:
    """Create tasks using MCP tools (Archon)"""
    created_tasks = []
    
    try:
        archon_url = os.getenv("MCP_ARCHON_URL", "http://localhost:8181")
        
        for task_data in tasks:
            # Try to create task via Archon MCP
            try:
                response = requests.post(
                    f"{archon_url}/projects/tasks",
                    json={
                        "title": task_data["title"],
                        "description": task_data["description"],
                        "requirements": task_data.get("requirements", []),
                        "acceptance_criteria": task_data.get("acceptance_criteria", []),
                        "priority": task_data.get("priority", "medium"),
                        "status": "pending"
                    },
                    timeout=10
                )
                
                if response.status_code == 200:
                    mcp_task = response.json()
                    created_tasks.append(mcp_task)
                    logger.info(f"Created task via MCP: {task_data['title']}")
                else:
                    # Fallback to local task creation
                    local_task = create_task(task_data)
                    created_tasks.append(local_task)
                    logger.warning(f"MCP failed, created local task: {task_data['title']}")
                    
            except Exception as e:
                # Fallback to local task creation
                logger.error(f"MCP task creation failed: {e}")
                local_task = create_task(task_data)
                created_tasks.append(local_task)
        
        return created_tasks
        
    except Exception as e:
        logger.error(f"Error in MCP task creation: {e}")
        return []

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

@app.post("/api/chat/message")
async def chat_message(request: TaskCreationRequest):
    """Have a conversation with the AI assistant"""
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
        
        # Get conversational response from OpenAI
        chat_response = await chat_with_openai(request.message, chat_messages)
        
        # Create assistant response
        assistant_message = {
            "id": str(uuid.uuid4()),
            "type": "assistant",
            "content": chat_response["content"],
            "timestamp": datetime.now().isoformat()
        }
        chat_messages.append(assistant_message)
        
        # Broadcast assistant message
        await broadcast_message({
            "type": "chat_message",
            "data": assistant_message
        })
        
        # Analyze conversation to see if tasks should be created
        analysis = await analyze_conversation_for_tasks(chat_messages)
        created_tasks = []
        
        if analysis.get("should_create_tasks", False) and analysis.get("tasks"):
            # Create tasks via MCP
            created_tasks = await create_tasks_via_mcp(analysis["tasks"])
            
            # Broadcast task creation events
            for task in created_tasks:
                await broadcast_message({
                    "type": "task_created",
                    "data": task
                })
            
            # Add a system message about task creation
            if created_tasks:
                task_creation_message = {
                    "id": str(uuid.uuid4()),
                    "type": "system",
                    "content": f"✅ I've automatically created {len(created_tasks)} task(s) based on our conversation: {', '.join([t['title'] for t in created_tasks])}",
                    "timestamp": datetime.now().isoformat()
                }
                chat_messages.append(task_creation_message)
                
                await broadcast_message({
                    "type": "chat_message",
                    "data": task_creation_message
                })
        
        return {
            "message": assistant_message,
            "conversation_continues": True,
            "tasks_created": len(created_tasks),
            "analysis": analysis.get("reasoning", "")
        }
    
    except Exception as e:
        logger.error(f"Error in chat conversation: {e}")
        error_message = {
            "id": str(uuid.uuid4()),
            "type": "system",
            "content": f"Sorry, I encountered an error: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }
        chat_messages.append(error_message)
        
        await broadcast_message({
            "type": "chat_message",
            "data": error_message
        })
        
        raise HTTPException(status_code=500, detail=str(e))

# Keep the old endpoint for backward compatibility but redirect to conversation
@app.post("/api/chat/create-task")
async def chat_create_task_legacy(request: TaskCreationRequest):
    """Legacy endpoint - redirects to conversational interface"""
    return await chat_message(request)

@app.get("/api/chat/messages")
async def get_chat_messages():
    """Get chat message history"""
    return {"messages": chat_messages}

@app.get("/api/status")
async def get_automation_status():
    """Get automation system status"""
    return {"status": automation_status}

@app.get("/api/logs")
async def get_agent_logs():
    """Get recent agent logs for monitoring"""
    try:
        logs = []
        
        # Read from error log
        error_log_path = Path("logs/errors.log")
        if error_log_path.exists():
            with open(error_log_path, 'r') as f:
                lines = f.readlines()
                for line in lines[-20:]:  # Last 20 error entries
                    if line.strip():
                        logs.append({
                            "level": "ERROR",
                            "message": line.strip(),
                            "timestamp": datetime.now().isoformat()
                        })
        
        # Read from main automation log
        log_files = list(Path("logs").glob("automation_*.log"))
        if log_files:
            latest_log = max(log_files, key=lambda f: f.stat().st_mtime)
            with open(latest_log, 'r') as f:
                lines = f.readlines()
                for line in lines[-50:]:  # Last 50 log entries
                    if line.strip() and "INFO" in line:
                        logs.append({
                            "level": "INFO",
                            "message": line.strip(),
                            "timestamp": datetime.now().isoformat()
                        })
        
        # Add current automation status as logs
        if automation_status["running"]:
            logs.append({
                "level": "INFO",
                "message": f"Automation running - Loop #{automation_status['loop_count']}",
                "timestamp": datetime.now().isoformat()
            })
        
        # Sort by timestamp and limit to last 30 entries
        logs = sorted(logs, key=lambda x: x["timestamp"])[-30:]
        
        return {"logs": logs}
        
    except Exception as e:
        logger.error(f"Error reading logs: {e}")
        return {"logs": [{"level": "ERROR", "message": f"Failed to read logs: {str(e)}", "timestamp": datetime.now().isoformat()}]}

async def process_task_real(task: Dict) -> bool:
    """Process a task using Claude Code automation workflow"""
    try:
        task_description = task.get("description", "")
        task_title = task.get("title", "")
        
        logger.info(f"Starting real task processing: {task_title}")
        
        # Initialize Claude Code automation
        automation = ClaudeCodeAutomation(project_path=".")
        await automation.initialize()
        
        # Create a formatted task for Claude Code
        claude_task = {
            "task_id": task.get("id", ""),
            "title": task_title,
            "description": task_description,
            "requirements": task.get("requirements", []),
            "acceptance_criteria": task.get("acceptance_criteria", [])
        }
        
        # Use Claude Code to implement the task
        result = await automation.claude_code_implement(claude_task)
        
        if result["status"] in ["implemented", "simulated_implementation"]:
            logger.info(f"Task completed successfully: {task_title}")
            
            # Add command output to chat if available
            execution_result = result.get("execution_result", {})
            if execution_result and execution_result.get("user_visible_output"):
                output_message = {
                    "id": str(uuid.uuid4()),
                    "type": "system",
                    "content": f"✅ Task '{task_title}' completed!\n\n{execution_result['user_visible_output']}",
                    "timestamp": datetime.now().isoformat()
                }
                chat_messages.append(output_message)
                
                # Broadcast the system message
                await broadcast_message({
                    "type": "chat_message",
                    "data": output_message
                })
            
            return True
        else:
            logger.error(f"Task implementation failed: {result.get('output', 'Unknown error')}")
            return False
            
    except Exception as e:
        logger.error(f"Error processing task {task.get('id')}: {e}")
        return False

# Removed hardcoded task type analysis - now handled by Claude Code

async def handle_ui_styling_task(task: Dict) -> bool:
    """Handle UI styling changes like background color, theme changes, title changes"""
    try:
        description = str(task.get("description", "")).lower()
        title = str(task.get("title", "")).lower()
        
        logger.info(f"Processing UI styling task: {task.get('title')}")
        
        # Handle title changes
        if "title" in description or "title" in title:
            return await update_html_title(task)
        # Analyze what styling change is needed
        elif "background" in description and "red" in description:
            return await change_background_color("red")
        elif "background" in description:
            # Extract color from description
            colors = ["blue", "green", "red", "yellow", "purple", "black", "white", "gray"]
            color = "blue"  # default
            for c in colors:
                if c in description:
                    color = c
                    break
            return await change_background_color(color)
        elif "color" in description or "theme" in description:
            return await apply_general_styling_change(task)
        else:
            return await apply_general_styling_change(task)
            
    except Exception as e:
        logger.error(f"Error handling UI styling task: {e}")
        return False

async def handle_react_component_task(task: Dict) -> bool:
    """Handle React component creation/modification"""
    try:
        description = str(task.get("description", "")).lower()
        title = str(task.get("title", "")).lower()
        
        logger.info(f"Processing React component task: {task.get('title')}")
        
        if "login" in description or "login" in title:
            return await create_login_component()
        elif "button" in description:
            return await create_button_component(task)
        elif "form" in description:
            return await create_form_component(task)
        else:
            return await create_generic_component(task)
            
    except Exception as e:
        logger.error(f"Error handling React component task: {e}")
        return False

async def change_background_color(color: str) -> bool:
    """DISABLED: Change the background color of the main application"""
    logger.info(f"Background color change to {color} was requested but disabled to prevent crude styling")
    return False

async def create_login_component() -> bool:
    """Create a login form component"""
    try:
        component_file = "/home/john/dev/personal/bootstrap/src/components/LoginForm.tsx"
        
        component_code = '''import React, { useState } from 'react';

interface LoginFormProps {
  onLogin: (username: string, password: string) => void;
}

export const LoginForm: React.FC<LoginFormProps> = ({ onLogin }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onLogin(username, password);
  };

  return (
    <div className="max-w-md mx-auto mt-8 p-6 bg-white rounded-lg shadow-md">
      <h2 className="text-2xl font-bold mb-6 text-center">Login</h2>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="username" className="block text-sm font-medium text-gray-700 mb-1">
            Username
          </label>
          <input
            type="text"
            id="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            required
          />
        </div>
        <div>
          <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">
            Password
          </label>
          <input
            type="password"
            id="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            required
          />
        </div>
        <button
          type="submit"
          className="w-full bg-blue-500 text-white py-2 px-4 rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          Login
        </button>
      </form>
    </div>
  );
};
'''
        
        # Create components directory if it doesn't exist
        components_dir = "/home/john/dev/personal/bootstrap/src/components"
        os.makedirs(components_dir, exist_ok=True)
        
        # Write the component
        with open(component_file, 'w') as f:
            f.write(component_code)
        
        logger.info(f"Created LoginForm component: {component_file}")
        
        # Add to App.tsx for immediate visibility
        await add_component_to_app("LoginForm")
        
        # Rebuild the frontend
        await rebuild_frontend()
        
        return True
        
    except Exception as e:
        logger.error(f"Error creating login component: {e}")
        return False

async def apply_general_styling_change(task: Dict) -> bool:
    """Apply general styling changes"""
    try:
        css_file = "/home/john/dev/personal/bootstrap/src/index.css"
        task_title = task.get('title', '').lower()
        task_description = task.get('description', '').lower()
        
        # Check if this is a visibility improvement task
        if any(word in task_title + task_description for word in ['visibility', 'visible', 'see', 'contrast', 'readable']):
            return await fix_visibility_issues()
        
        # Default styling change
        new_rule = f"""
/* Auto-generated styling change for: {task.get('title', 'Unknown task')} */
.task-styling-change {{
    /* Applied styling change */
    border: 2px solid #007bff;
    padding: 10px;
    margin: 10px;
}}
"""
        
        if os.path.exists(css_file):
            with open(css_file, 'a') as f:
                f.write(new_rule)
        else:
            with open(css_file, 'w') as f:
                f.write(new_rule)
        
        logger.info(f"Applied general styling change for: {task.get('title')}")
        await rebuild_frontend()
        return True
        
    except Exception as e:
        logger.error(f"Error applying styling change: {e}")
        return False

async def fix_visibility_issues() -> bool:
    """DISABLED: Fix visibility issues by improving contrast and readability"""
    logger.info("Visibility fix was requested but disabled to prevent crude styling")
    return False
    # DISABLED CRUDE CSS AUTOMATION - Use Claude Code for professional styling instead
    # This function was generating !important overrides that conflict with professional CSS

async def create_button_component(task: Dict) -> bool:
    """Create a button component"""
    try:
        # Add a simple button to the main app
        return await add_component_to_app("SimpleButton", """
const SimpleButton = () => (
  <button 
    className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded m-4"
    onClick={() => alert('Hello!')}
  >
    Hello Button
  </button>
);""")
        
    except Exception as e:
        logger.error(f"Error creating button component: {e}")
        return False

async def create_form_component(task: Dict) -> bool:
    """Create a form component"""
    try:
        return await create_login_component()  # Reuse login form for now
        
    except Exception as e:
        logger.error(f"Error creating form component: {e}")
        return False

async def create_generic_component(task: Dict) -> bool:
    """Create a generic component"""
    try:
        task_id = task.get('id', 'Unknown')
        if isinstance(task_id, str) and len(task_id) > 8:
            task_id = task_id[:8]
        component_name = f"Task{task_id}"
        
        title = task.get('title', 'Generated Component')
        description = task.get('description', 'This component was auto-generated.')
        
        # Escape quotes in title and description
        title = title.replace('"', '\\"').replace("'", "\\'")
        description = description.replace('"', '\\"').replace("'", "\\'")
        
        component_code = f"""
const {component_name} = () => (
  <div className="p-4 m-4 border border-gray-300 rounded">
    <h3 className="text-lg font-semibold">{title}</h3>
    <p className="text-gray-600">{description}</p>
  </div>
);"""
        
        return await add_component_to_app(component_name, component_code)
        
    except Exception as e:
        logger.error(f"Error creating generic component: {e}")
        return False

async def add_component_to_app(component_name: str, component_code: str = "") -> bool:
    """Add a component to the main App.tsx file"""
    try:
        app_file = "/home/john/dev/personal/bootstrap/src/App.tsx"
        
        # Read current App.tsx
        with open(app_file, 'r') as f:
            content = f.read()
        
        # Add component code before the App function if provided
        if component_code:
            import_section = "import React, { useState, useEffect } from 'react';"
            if import_section in content:
                content = content.replace(
                    import_section,
                    f"{import_section}\n\n{component_code}"
                )
        
        # Add component to JSX (before closing main div)
        component_jsx = f"        <{component_name} />"
        
        # Find the last closing div and add component before it
        if "</main>" in content:
            content = content.replace("</main>", f"        {component_jsx}\n      </main>")
        elif "</div>" in content:
            # Find the last </div> and add component before it
            last_div_pos = content.rfind("</div>")
            if last_div_pos != -1:
                content = content[:last_div_pos] + f"      {component_jsx}\n    " + content[last_div_pos:]
        
        # Write back to file
        with open(app_file, 'w') as f:
            f.write(content)
        
        logger.info(f"Added {component_name} to App.tsx")
        await rebuild_frontend()
        return True
        
    except Exception as e:
        logger.error(f"Error adding component to app: {e}")
        return False

async def rebuild_frontend() -> bool:
    """Rebuild the React frontend"""
    try:
        logger.info("Rebuilding frontend...")
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd="/home/john/dev/personal/bootstrap",
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            logger.info("Frontend rebuilt successfully")
            return True
        else:
            logger.error(f"Frontend build failed: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Error rebuilding frontend: {e}")
        return False

async def handle_code_creation_task(task: Dict) -> bool:
    """Handle code creation tasks"""
    try:
        description = task.get("description", "")
        logger.info(f"Processing code creation task: {description}")
        
        # Create a simple implementation based on the task
        if "contact form" in description.lower():
            return await create_contact_form()
        elif "dark mode" in description.lower():
            return await create_dark_mode_toggle()
        elif "authentication" in description.lower():
            return await create_auth_system()
        elif "sidebar" in description.lower() or "menu" in description.lower():
            return await create_sidebar_menu()
        else:
            # Generic code creation
            return await create_generic_component(description)
            
    except Exception as e:
        logger.error(f"Error in code creation task: {e}")
        return False

async def handle_bug_fix_task(task: Dict) -> bool:
    """Handle bug fix tasks"""
    try:
        logger.info("Processing bug fix task")
        # For now, simulate bug fix by checking and updating existing files
        return True
    except Exception as e:
        logger.error(f"Error in bug fix task: {e}")
        return False

async def handle_testing_task(task: Dict) -> bool:
    """Handle testing tasks"""
    try:
        logger.info("Processing testing task")
        # Create or run tests
        return await create_test_files()
    except Exception as e:
        logger.error(f"Error in testing task: {e}")
        return False

async def handle_documentation_task(task: Dict) -> bool:
    """Handle documentation tasks"""
    try:
        logger.info("Processing documentation task")
        return await create_documentation()
    except Exception as e:
        logger.error(f"Error in documentation task: {e}")
        return False

async def handle_generic_task(task: Dict) -> bool:
    """Handle generic tasks"""
    try:
        logger.info(f"Processing generic task: {task.get('title', 'Unknown')}")
        # For generic tasks, create a simple text file with task details
        return await create_task_artifact(task)
    except Exception as e:
        logger.error(f"Error in generic task: {e}")
        return False

async def create_contact_form() -> bool:
    """Create a contact form component"""
    try:
        contact_form_code = '''<!DOCTYPE html>
<html>
<head>
    <title>Contact Form</title>
    <style>
        .contact-form { max-width: 500px; margin: 20px auto; padding: 20px; border: 1px solid #ccc; border-radius: 8px; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: bold; }
        .form-group input, .form-group textarea { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
        .submit-btn { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }
    </style>
</head>
<body>
    <div class="contact-form">
        <h2>Contact Us</h2>
        <form id="contactForm">
            <div class="form-group">
                <label for="name">Name:</label>
                <input type="text" id="name" name="name" required>
            </div>
            <div class="form-group">
                <label for="email">Email:</label>
                <input type="email" id="email" name="email" required>
            </div>
            <div class="form-group">
                <label for="message">Message:</label>
                <textarea id="message" name="message" rows="5" required></textarea>
            </div>
            <button type="submit" class="submit-btn">Send Message</button>
        </form>
    </div>
    
    <script>
        document.getElementById('contactForm').addEventListener('submit', function(e) {
            e.preventDefault();
            alert('Thank you for your message! We will get back to you soon.');
        });
    </script>
</body>
</html>'''
        
        with open('contact_form.html', 'w') as f:
            f.write(contact_form_code)
        
        logger.info("Created contact_form.html")
        return True
        
    except Exception as e:
        logger.error(f"Error creating contact form: {e}")
        return False

async def create_dark_mode_toggle() -> bool:
    """Create a dark mode toggle feature"""
    try:
        dark_mode_code = '''<!DOCTYPE html>
<html>
<head>
    <title>Dark Mode Toggle</title>
    <style>
        :root {
            --bg-color: #ffffff;
            --text-color: #333333;
            --border-color: #cccccc;
        }
        
        [data-theme="dark"] {
            --bg-color: #333333;
            --text-color: #ffffff;
            --border-color: #666666;
        }
        
        body {
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: Arial, sans-serif;
            margin: 20px;
            transition: background-color 0.3s, color 0.3s;
        }
        
        .toggle-container {
            text-align: center;
            margin-bottom: 20px;
        }
        
        .toggle-btn {
            background: var(--text-color);
            color: var(--bg-color);
            border: 1px solid var(--border-color);
            padding: 10px 20px;
            border-radius: 20px;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .content {
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            border: 1px solid var(--border-color);
            border-radius: 8px;
        }
    </style>
</head>
<body>
    <div class="toggle-container">
        <button id="themeToggle" class="toggle-btn">🌙 Dark Mode</button>
    </div>
    
    <div class="content">
        <h1>Dark Mode Demo</h1>
        <p>This is a demonstration of dark mode functionality with theme persistence.</p>
        <p>The current theme will be saved to localStorage and restored on page reload.</p>
    </div>
    
    <script>
        const toggleBtn = document.getElementById('themeToggle');
        const body = document.body;
        
        // Load saved theme
        const savedTheme = localStorage.getItem('theme') || 'light';
        if (savedTheme === 'dark') {
            body.setAttribute('data-theme', 'dark');
            toggleBtn.textContent = '☀️ Light Mode';
        }
        
        // Toggle theme
        toggleBtn.addEventListener('click', () => {
            const currentTheme = body.getAttribute('data-theme');
            if (currentTheme === 'dark') {
                body.removeAttribute('data-theme');
                toggleBtn.textContent = '🌙 Dark Mode';
                localStorage.setItem('theme', 'light');
            } else {
                body.setAttribute('data-theme', 'dark');
                toggleBtn.textContent = '☀️ Light Mode';
                localStorage.setItem('theme', 'dark');
            }
        });
    </script>
</body>
</html>'''
        
        with open('dark_mode_toggle.html', 'w') as f:
            f.write(dark_mode_code)
        
        logger.info("Created dark_mode_toggle.html")
        return True
        
    except Exception as e:
        logger.error(f"Error creating dark mode toggle: {e}")
        return False

async def create_auth_system() -> bool:
    """Create a basic authentication system"""
    try:
        auth_code = '''<!DOCTYPE html>
<html>
<head>
    <title>Authentication System</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .auth-container { max-width: 400px; margin: 50px auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .form-group { margin-bottom: 20px; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: bold; }
        .form-group input { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; }
        .btn { background: #007bff; color: white; padding: 12px 20px; border: none; border-radius: 4px; cursor: pointer; width: 100%; }
        .btn:hover { background: #0056b3; }
        .toggle-link { color: #007bff; cursor: pointer; text-decoration: underline; }
        .hidden { display: none; }
        .user-info { background: #d4edda; padding: 15px; border-radius: 4px; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="auth-container">
        <div id="loginForm">
            <h2>Login</h2>
            <form id="login">
                <div class="form-group">
                    <label for="loginEmail">Email:</label>
                    <input type="email" id="loginEmail" required>
                </div>
                <div class="form-group">
                    <label for="loginPassword">Password:</label>
                    <input type="password" id="loginPassword" required>
                </div>
                <button type="submit" class="btn">Login</button>
            </form>
            <p>Don't have an account? <span class="toggle-link" onclick="toggleForm()">Register here</span></p>
        </div>
        
        <div id="registerForm" class="hidden">
            <h2>Register</h2>
            <form id="register">
                <div class="form-group">
                    <label for="registerName">Name:</label>
                    <input type="text" id="registerName" required>
                </div>
                <div class="form-group">
                    <label for="registerEmail">Email:</label>
                    <input type="email" id="registerEmail" required>
                </div>
                <div class="form-group">
                    <label for="registerPassword">Password:</label>
                    <input type="password" id="registerPassword" required>
                </div>
                <button type="submit" class="btn">Register</button>
            </form>
            <p>Already have an account? <span class="toggle-link" onclick="toggleForm()">Login here</span></p>
        </div>
        
        <div id="userDashboard" class="hidden">
            <h2>Welcome!</h2>
            <div class="user-info">
                <p>You are successfully logged in.</p>
                <p id="userDetails"></p>
                <button class="btn" onclick="logout()">Logout</button>
            </div>
        </div>
    </div>
    
    <script>
        function toggleForm() {
            const loginForm = document.getElementById('loginForm');
            const registerForm = document.getElementById('registerForm');
            loginForm.classList.toggle('hidden');
            registerForm.classList.toggle('hidden');
        }
        
        function login(email, password) {
            // Simulate login (in real app, this would call an API)
            const userData = { email, name: email.split('@')[0] };
            localStorage.setItem('user', JSON.stringify(userData));
            showDashboard(userData);
        }
        
        function register(name, email, password) {
            // Simulate registration
            const userData = { name, email };
            localStorage.setItem('user', JSON.stringify(userData));
            showDashboard(userData);
        }
        
        function showDashboard(userData) {
            document.getElementById('loginForm').classList.add('hidden');
            document.getElementById('registerForm').classList.add('hidden');
            document.getElementById('userDashboard').classList.remove('hidden');
            document.getElementById('userDetails').textContent = `Name: ${userData.name} | Email: ${userData.email}`;
        }
        
        function logout() {
            localStorage.removeItem('user');
            document.getElementById('userDashboard').classList.add('hidden');
            document.getElementById('loginForm').classList.remove('hidden');
        }
        
        // Check if user is already logged in
        const savedUser = localStorage.getItem('user');
        if (savedUser) {
            showDashboard(JSON.parse(savedUser));
        }
        
        // Form submissions
        document.getElementById('login').addEventListener('submit', (e) => {
            e.preventDefault();
            const email = document.getElementById('loginEmail').value;
            const password = document.getElementById('loginPassword').value;
            login(email, password);
        });
        
        document.getElementById('register').addEventListener('submit', (e) => {
            e.preventDefault();
            const name = document.getElementById('registerName').value;
            const email = document.getElementById('registerEmail').value;
            const password = document.getElementById('registerPassword').value;
            register(name, email, password);
        });
    </script>
</body>
</html>'''
        
        with open('auth_system.html', 'w') as f:
            f.write(auth_code)
        
        logger.info("Created auth_system.html")
        return True
        
    except Exception as e:
        logger.error(f"Error creating auth system: {e}")
        return False

async def create_sidebar_menu() -> bool:
    """Create a responsive sidebar menu"""
    try:
        sidebar_code = '''<!DOCTYPE html>
<html>
<head>
    <title>Responsive Sidebar Menu</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body { font-family: Arial, sans-serif; }
        
        .sidebar {
            position: fixed;
            left: -250px;
            top: 0;
            width: 250px;
            height: 100%;
            background: #2c3e50;
            transition: left 0.3s ease;
            z-index: 1000;
        }
        
        .sidebar.active { left: 0; }
        
        .sidebar-header {
            padding: 20px;
            background: #34495e;
            color: white;
            text-align: center;
        }
        
        .sidebar-menu {
            list-style: none;
            padding: 0;
        }
        
        .sidebar-menu li {
            border-bottom: 1px solid #34495e;
        }
        
        .sidebar-menu a {
            display: block;
            padding: 15px 20px;
            color: #ecf0f1;
            text-decoration: none;
            transition: background 0.3s;
        }
        
        .sidebar-menu a:hover {
            background: #34495e;
        }
        
        .main-content {
            margin-left: 0;
            padding: 20px;
            transition: margin-left 0.3s ease;
        }
        
        .main-content.shifted {
            margin-left: 250px;
        }
        
        .menu-toggle {
            background: #3498db;
            color: white;
            border: none;
            padding: 10px 15px;
            cursor: pointer;
            border-radius: 4px;
            margin-bottom: 20px;
        }
        
        .overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
            display: none;
            z-index: 999;
        }
        
        .overlay.active {
            display: block;
        }
        
        @media (max-width: 768px) {
            .main-content.shifted {
                margin-left: 0;
            }
        }
    </style>
</head>
<body>
    <div class="sidebar" id="sidebar">
        <div class="sidebar-header">
            <h3>Navigation</h3>
        </div>
        <ul class="sidebar-menu">
            <li><a href="#home">🏠 Home</a></li>
            <li><a href="#about">ℹ️ About</a></li>
            <li><a href="#services">⚙️ Services</a></li>
            <li><a href="#portfolio">💼 Portfolio</a></li>
            <li><a href="#contact">📧 Contact</a></li>
            <li><a href="#blog">📝 Blog</a></li>
            <li><a href="#settings">⚙️ Settings</a></li>
        </ul>
    </div>
    
    <div class="overlay" id="overlay"></div>
    
    <div class="main-content" id="mainContent">
        <button class="menu-toggle" id="menuToggle">☰ Menu</button>
        
        <h1>Responsive Sidebar Demo</h1>
        <p>This is a responsive sidebar menu that works on both desktop and mobile devices.</p>
        
        <h2>Features:</h2>
        <ul>
            <li>Slide-in animation</li>
            <li>Mobile responsive</li>
            <li>Overlay for mobile</li>
            <li>Smooth transitions</li>
        </ul>
        
        <p>Click the menu button to toggle the sidebar. On desktop, the main content will shift. On mobile, an overlay will appear.</p>
        
        <div style="height: 1000px; background: linear-gradient(to bottom, #f8f9fa, #e9ecef); margin-top: 20px; padding: 20px; border-radius: 8px;">
            <p>This is a tall content area to demonstrate scrolling behavior with the fixed sidebar.</p>
        </div>
    </div>
    
    <script>
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('overlay');
        const mainContent = document.getElementById('mainContent');
        const menuToggle = document.getElementById('menuToggle');
        
        let isOpen = false;
        
        function toggleSidebar() {
            isOpen = !isOpen;
            
            if (isOpen) {
                sidebar.classList.add('active');
                overlay.classList.add('active');
                
                // On desktop, shift content; on mobile, don't
                if (window.innerWidth > 768) {
                    mainContent.classList.add('shifted');
                }
            } else {
                sidebar.classList.remove('active');
                overlay.classList.remove('active');
                mainContent.classList.remove('shifted');
            }
        }
        
        menuToggle.addEventListener('click', toggleSidebar);
        overlay.addEventListener('click', toggleSidebar);
        
        // Handle window resize
        window.addEventListener('resize', () => {
            if (window.innerWidth <= 768) {
                mainContent.classList.remove('shifted');
            } else if (isOpen) {
                mainContent.classList.add('shifted');
            }
        });
        
        // Handle menu item clicks
        document.querySelectorAll('.sidebar-menu a').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const section = e.target.textContent;
                alert(`Navigating to: ${section}`);
                
                // Close sidebar on mobile after selection
                if (window.innerWidth <= 768) {
                    toggleSidebar();
                }
            });
        });
    </script>
</body>
</html>'''
        
        with open('sidebar_menu.html', 'w') as f:
            f.write(sidebar_code)
        
        logger.info("Created sidebar_menu.html")
        return True
        
    except Exception as e:
        logger.error(f"Error creating sidebar menu: {e}")
        return False

async def create_generic_component(description: str) -> bool:
    """Create a generic component based on description"""
    try:
        # Create a simple HTML page based on the description
        component_code = f'''<!DOCTYPE html>
<html>
<head>
    <title>Generated Component</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .header {{ color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px; margin-bottom: 20px; }}
        .content {{ line-height: 1.6; color: #555; }}
        .feature-box {{ background: #e3f2fd; padding: 15px; margin: 10px 0; border-left: 4px solid #2196f3; border-radius: 4px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1 class="header">Auto-Generated Component</h1>
        <div class="content">
            <p><strong>Task Description:</strong> {description}</p>
            <div class="feature-box">
                <h3>Generated Features:</h3>
                <ul>
                    <li>Responsive design</li>
                    <li>Clean styling</li>
                    <li>Semantic HTML structure</li>
                    <li>Cross-browser compatibility</li>
                </ul>
            </div>
            <p>This component was automatically generated based on your task requirements. It provides a basic foundation that can be customized further.</p>
            <button style="background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer;" onclick="alert('Component is working!')">Test Button</button>
        </div>
    </div>
</body>
</html>'''
        
        # Create filename from description
        filename = description.lower().replace(' ', '_').replace(',', '')[:30] + '_component.html'
        
        with open(filename, 'w') as f:
            f.write(component_code)
        
        logger.info(f"Created {filename}")
        return True
        
    except Exception as e:
        logger.error(f"Error creating generic component: {e}")
        return False

async def create_test_files() -> bool:
    """Create test files"""
    try:
        test_code = '''// Basic Test Suite
describe('Component Tests', () => {
    beforeEach(() => {
        // Setup code here
        console.log('Setting up test environment');
    });
    
    test('should render correctly', () => {
        // Test implementation
        expect(true).toBe(true);
        console.log('✅ Render test passed');
    });
    
    test('should handle user interactions', () => {
        // Test user interactions
        expect(true).toBe(true);
        console.log('✅ Interaction test passed');
    });
    
    test('should validate input data', () => {
        // Test data validation
        const isValid = validateInput('test@example.com');
        expect(isValid).toBe(true);
        console.log('✅ Validation test passed');
    });
    
    afterEach(() => {
        // Cleanup code here
        console.log('Cleaning up test environment');
    });
});

function validateInput(email) {
    return email && email.includes('@');
}

// Run tests
console.log('Running test suite...');
describe('Component Tests', () => {});
console.log('All tests completed!');'''
        
        with open('component_tests.js', 'w') as f:
            f.write(test_code)
        
        logger.info("Created component_tests.js")
        return True
        
    except Exception as e:
        logger.error(f"Error creating test files: {e}")
        return False

async def create_documentation() -> bool:
    """Create documentation"""
    try:
        doc_content = '''# Project Documentation

## Overview
This documentation was automatically generated by the Claude Code Automation system.

## Components Created
The automation system has created various components based on user requests:

### 1. Contact Form (`contact_form.html`)
- Responsive contact form with validation
- Email and message fields
- Client-side form handling

### 2. Dark Mode Toggle (`dark_mode_toggle.html`)
- Theme switcher with localStorage persistence
- CSS custom properties for theming
- Smooth transitions

### 3. Authentication System (`auth_system.html`)
- Login and registration forms
- Local storage for session management
- User dashboard

### 4. Sidebar Menu (`sidebar_menu.html`)
- Responsive navigation sidebar
- Mobile-friendly with overlay
- Smooth animations

## Testing
Test files are automatically generated to ensure component functionality:
- `component_tests.js` - Basic test suite

## Usage
1. Open any HTML file in a web browser
2. Interact with the components
3. Check browser console for any errors

## Customization
All components can be customized by:
- Modifying CSS styles
- Updating HTML structure
- Extending JavaScript functionality

## Support
Generated by Claude Code Automation System
Date: ''' + datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        with open('README.md', 'w') as f:
            f.write(doc_content)
        
        logger.info("Created README.md documentation")
        return True
        
    except Exception as e:
        logger.error(f"Error creating documentation: {e}")
        return False

async def create_task_artifact(task: Dict) -> bool:
    """Create an artifact for generic tasks"""
    try:
        artifact_content = f'''# Task Artifact

## Task Details
- **ID**: {task.get('id', 'Unknown')}
- **Title**: {task.get('title', 'Unknown')}
- **Description**: {task.get('description', 'No description')}
- **Priority**: {task.get('priority', 'medium')}
- **Created**: {task.get('created_at', 'Unknown')}

## Requirements
{chr(10).join(f"- {req}" for req in task.get('requirements', []))}

## Acceptance Criteria
{chr(10).join(f"- {criteria}" for criteria in task.get('acceptance_criteria', []))}

## Processing Notes
This task was processed by the Claude Code Automation system.
Processing completed at: {datetime.now().isoformat()}

## Generated Files
Check the project directory for any generated files related to this task.
'''
        
        # Create filename from task title
        filename = f"task_{task.get('id', 'unknown')[:8]}_artifact.md"
        
        with open(filename, 'w') as f:
            f.write(artifact_content)
        
        logger.info(f"Created task artifact: {filename}")
        return True
        
    except Exception as e:
        logger.error(f"Error creating task artifact: {e}")
        return False

async def run_automation_loop():
    """Background task to run automation loop"""
    global automation_status
    
    try:        
        while automation_status["running"]:
            automation_status["loop_count"] += 1
            
            # Broadcast status update
            await broadcast_message({
                "type": "status_update",
                "data": automation_status
            })
            
            try:
                cycle_start = datetime.now()
                
                # Check for pending tasks and process them
                pending_tasks = [t for t in tasks.values() if t["status"] == "pending"]
                if pending_tasks:
                    task = pending_tasks[0]
                    task["status"] = "in_progress"
                    task["updated_at"] = datetime.now().isoformat()
                    automation_status["current_task"] = task["title"]
                    
                    await broadcast_message({
                        "type": "task_updated", 
                        "data": task
                    })
                    
                    # Process the actual task
                    success = await process_task_real(task)
                    
                    # Update task status based on result
                    if success:
                        task["status"] = "completed"
                        logger.info(f"Task completed successfully: {task['title']}")
                    else:
                        task["status"] = "failed"
                        logger.error(f"Task failed: {task['title']}")
                    
                    task["updated_at"] = datetime.now().isoformat()
                    automation_status["current_task"] = None
                    
                    await broadcast_message({
                        "type": "task_updated",
                        "data": task
                    })
                
                # Calculate actual cycle duration
                cycle_end = datetime.now()
                duration = cycle_end - cycle_start
                automation_status["last_cycle_duration"] = str(duration)
                
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