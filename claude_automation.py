#!/usr/bin/env python3
"""
Automated Development Workflow with Claude Code
This script orchestrates the complete development cycle using Claude Code and Archon MCP server.
"""

import asyncio
import json
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging
from datetime import datetime

# Enhanced logging configuration with file output
def setup_logging():
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    simple_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    
    # File handler for all logs
    file_handler = logging.FileHandler(
        log_dir / f"automation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    
    # Error file handler
    error_handler = logging.FileHandler(log_dir / "errors.log")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)
    
    return root_logger

logger = setup_logging()

class ClaudeCodeAutomation:
    def __init__(self, project_path: str, archon_config: Optional[Dict] = None):
        self.project_path = Path(project_path)
        self.archon_config = archon_config or {}
        self.claude_code_session = None
        self.simulation_mode = False
        self.claude_code_cmd = None
        
    async def initialize(self):
        """Initialize automation system with OpenAI API and development tools"""
        logger.info("Initializing development automation system...")
        
        # We no longer need Claude Code CLI - using OpenAI API directly
        self.simulation_mode = False
        
        # Verify OpenAI API key is available
        import os
        if not os.getenv("OPENAI_API_KEY"):
            logger.warning("OPENAI_API_KEY not found. Tasks will fail.")
        
        # Verify project directory exists
        if not self.project_path.exists():
            raise RuntimeError(f"Project path does not exist: {self.project_path}")
        
        # Check for essential project files
        package_json = self.project_path / "package.json"
        if package_json.exists():
            logger.info("Found package.json - React project detected")
        
        public_dir = self.project_path / "public"
        if public_dir.exists():
            logger.info("Found public directory")
        
        src_dir = self.project_path / "src"
        if src_dir.exists():
            logger.info("Found src directory")
        
        logger.info(f"Working in project directory: {self.project_path}")
        logger.info("Automation system initialized with direct development tools access")
        return True
    
    async def get_archon_task(self, task_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve task from local API server"""
        logger.info("Fetching task from API server...")
        
        try:
            import requests
            # Get pending tasks from our API server
            response = requests.get('http://localhost:8009/api/tasks')
            if response.status_code == 200:
                tasks = response.json()['tasks']
                # Find a pending task
                pending_tasks = [t for t in tasks if t['status'] == 'pending']
                if pending_tasks:
                    task = pending_tasks[0]
                    # Mark as in_progress
                    requests.patch(f'http://localhost:8009/api/tasks/{task["id"]}', 
                                 json={'status': 'in_progress'})
                    logger.info(f"Retrieved task: {task['title']}")
                    return task
                else:
                    logger.info("No pending tasks found")
                    return None
            else:
                logger.warning(f"Failed to fetch tasks: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error fetching tasks: {e}")
            return None
    
    async def claude_code_implement(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Use OpenAI API with development tools to implement the task"""
        logger.info(f"Starting implementation for task: {task['title']}")
        
        try:
            # Use OpenAI API to analyze and implement the task
            from openai import AsyncOpenAI
            import os
            
            # Initialize OpenAI client
            openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            
            # Get current project context using command line tools
            project_context = await self.get_project_context_with_cli()
            
            # Create a comprehensive prompt with actual project context
            implementation_prompt = f"""
You are an expert software developer with access to command line tools. Your task is to implement:

**Task**: {task['title']}
**Description**: {task['description']}

**Current Project Structure and Files**:
{project_context}

**Your Task**: 
Based on the project files above, provide SPECIFIC command line operations to implement: "{task['title']}"

**Response Format** - MUST follow this exact format:
ANALYSIS: Brief analysis of what needs to change

COMMANDS:
- command1
- command2
- command3

**Example Response**:
ANALYSIS: Need to list directory contents

COMMANDS:
- ls -la
- ls src
- find . -name "*.tsx"

**CRITICAL**: 
- Put each command on its own line starting with "- "
- Only include executable shell commands after "COMMANDS:"
- Use standard CLI tools: ls, cat, grep, sed, echo, mkdir, cp, mv, rm, git, npm
- Be very specific with the format - the system parses this automatically
"""

            response = await openai_client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": implementation_prompt}],
                temperature=0.3,
                max_tokens=2000
            )
            
            implementation_plan = response.choices[0].message.content
            logger.info(f"Generated implementation plan: {implementation_plan}")
            
            # Execute the CLI commands from the implementation plan
            execution_result = await self.execute_cli_commands(implementation_plan, task)
            
            return {
                "status": "implemented",
                "output": implementation_plan,
                "changes_made": execution_result.get("changes_made", "Implementation completed"),
                "execution_result": execution_result
            }
            
        except Exception as e:
            logger.error(f"Error during implementation: {e}")
            return {
                "status": "implementation_error", 
                "output": str(e),
                "changes_made": "Implementation failed"
            }
    
    async def execute_cli_commands(self, implementation_plan: str, task: Dict[str, Any]) -> Dict[str, Any]:
        """Parse the OpenAI response and execute the shell commands"""
        logger.info("Parsing and executing CLI commands from implementation plan...")
        
        commands_executed = []
        command_outputs = []
        
        try:
            import subprocess
            import re
            
            # Extract commands from the implementation plan
            lines = implementation_plan.split('\n')
            in_commands_section = False
            commands_to_execute = []
            
            for line in lines:
                line = line.strip()
                
                # Check if we're entering the COMMANDS section
                if line.upper() == 'COMMANDS:':
                    in_commands_section = True
                    continue
                
                # Stop if we hit another section (starts with capital letters like "ANALYSIS:")
                if in_commands_section and line and line[0].isupper() and ':' in line:
                    in_commands_section = False
                
                # Extract commands - look for lines starting with "- " in the commands section
                if in_commands_section and line.startswith('- '):
                    command = line[2:].strip()  # Remove "- " prefix
                    if command:
                        commands_to_execute.append(command)
                        logger.info(f"Found command: {command}")
            
            logger.info(f"Found {len(commands_to_execute)} commands to execute: {commands_to_execute}")
            
            # Execute each command
            for command in commands_to_execute:
                if not command or command.startswith('#'):  # Skip empty lines and comments
                    continue
                    
                try:
                    # Split command into parts for subprocess
                    cmd_parts = command.split()
                    if not cmd_parts:
                        continue
                    
                    logger.info(f"Executing command: {command}")
                    
                    result = subprocess.run(
                        cmd_parts,
                        cwd=self.project_path,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    
                    commands_executed.append(command)
                    
                    if result.stdout:
                        # For listing commands, show more output; for others, truncate reasonably
                        if any(cmd in command.lower() for cmd in ['ls', 'find', 'grep']):
                            output = result.stdout[:1000]  # Show up to 1000 chars for listing commands
                        else:
                            output = result.stdout[:500]   # Show up to 500 chars for other commands
                        
                        if len(result.stdout) > len(output):
                            output += "\n... (output truncated)"
                        
                        command_outputs.append(f"{command} → {output}")
                    
                    if result.stderr:
                        command_outputs.append(f"{command} → ERROR: {result.stderr[:300]}")
                        
                    if result.returncode != 0:
                        logger.warning(f"Command failed with return code {result.returncode}: {command}")
                    else:
                        logger.info(f"Command executed successfully: {command}")
                        
                except Exception as e:
                    logger.error(f"Error executing command '{command}': {e}")
                    command_outputs.append(f"{command} → FAILED: {str(e)}")
            
            # Create a summary of the results for the user
            if command_outputs:
                output_summary = "Command Results:\n" + "\n\n".join(command_outputs[:5])  # Show first 5 outputs with better spacing
            else:
                output_summary = f"Executed {len(commands_executed)} commands successfully"
            
            return {
                "status": "executed",
                "commands_executed": commands_executed,
                "command_outputs": command_outputs,
                "changes_made": output_summary,
                "user_visible_output": output_summary
            }
            
        except Exception as e:
            logger.error(f"Error executing CLI commands: {e}")
            return {
                "status": "execution_error",
                "error": str(e),
                "commands_executed": commands_executed,
                "command_outputs": command_outputs
            }
    
    async def execute_implementation_plan(self, implementation_plan: str, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the implementation plan by parsing and running the specified operations"""
        logger.info("Executing implementation plan...")
        
        changes_made = []
        commands_executed = []
        
        try:
            # For now, let's implement a simple approach that looks for common patterns
            # and executes basic file operations
            
            # Check if this is a title/HTML change
            if "title" in task['title'].lower() or "title" in str(task.get('description', '')).lower():
                result = await self.update_html_title(task, implementation_plan)
                changes_made.append(result)
            
            # Check if this is a color/styling change
            elif any(word in task['title'].lower() for word in ['color', 'theme', 'style', 'background']):
                result = await self.update_styles(task, implementation_plan)
                changes_made.append(result)
            
            # Check if this is a component/feature addition
            elif any(word in task['title'].lower() for word in ['component', 'button', 'form', 'add', 'create']):
                result = await self.add_component(task, implementation_plan)
                changes_made.append(result)
            
            # Generic implementation - create documentation/artifact
            else:
                result = await self.create_task_documentation(task, implementation_plan)
                changes_made.append(result)
            
            # Try to rebuild frontend if any frontend files were changed
            if any("frontend" in str(change) for change in changes_made):
                build_result = await self.rebuild_frontend()
                commands_executed.append(f"npm run build: {build_result}")
            
            return {
                "status": "executed",
                "changes_made": changes_made,
                "commands_executed": commands_executed
            }
            
        except Exception as e:
            logger.error(f"Error executing implementation plan: {e}")
            return {
                "status": "execution_error",
                "error": str(e),
                "changes_made": changes_made,
                "commands_executed": commands_executed
            }
    
    async def update_html_title(self, task: Dict[str, Any], plan: str) -> str:
        """Update the HTML title in index.html"""
        try:
            # Extract the new title from the task or plan
            task_text = f"{task['title']} {task.get('description', '')}"
            
            # Look for quoted strings that might be the new title
            import re
            title_matches = re.findall(r'["\']([^"\']*(?:automation|claude)[^"\']*)["\']', task_text.lower())
            
            if title_matches:
                new_title = title_matches[0].title()
            else:
                # Default fallback
                new_title = "Claude Code Automation v1"
            
            # Read current index.html
            html_file = self.project_path / "public" / "index.html"
            if html_file.exists():
                with open(html_file, 'r') as f:
                    content = f.read()
                
                # Update the title tag
                updated_content = re.sub(
                    r'<title>([^<]*)</title>',
                    f'<title>{new_title}</title>',
                    content
                )
                
                # Write back to file
                with open(html_file, 'w') as f:
                    f.write(updated_content)
                
                logger.info(f"Updated HTML title to '{new_title}' in {html_file}")
                return f"Updated HTML title to '{new_title}'"
            else:
                return "index.html not found"
                
        except Exception as e:
            logger.error(f"Error updating HTML title: {e}")
            return f"Error updating HTML title: {e}"
    
    async def update_styles(self, task: Dict[str, Any], plan: str) -> str:
        """Update CSS styles based on the task"""
        try:
            # Simple CSS update - add new styles to index.css
            css_file = self.project_path / "src" / "index.css"
            
            task_lower = task['title'].lower()
            new_styles = ""
            
            if "green" in task_lower:
                new_styles = """
/* Auto-generated green color scheme */
:root {
  --primary-color: #10b981;
  --secondary-color: #059669;
  --accent-color: #34d399;
}

.text-primary { color: var(--primary-color); }
.bg-primary { background-color: var(--primary-color); }
.border-primary { border-color: var(--primary-color); }
"""
            elif "blue" in task_lower:
                new_styles = """
/* Auto-generated blue color scheme */
:root {
  --primary-color: #3b82f6;
  --secondary-color: #1d4ed8;
  --accent-color: #60a5fa;
}

.text-primary { color: var(--primary-color); }
.bg-primary { background-color: var(--primary-color); }
.border-primary { border-color: var(--primary-color); }
"""
            else:
                # Generic color update
                new_styles = f"""
/* Auto-generated styles for: {task['title']} */
.task-style {{
  border: 2px solid #007bff;
  padding: 1rem;
  margin: 0.5rem 0;
  border-radius: 0.5rem;
}}
"""
            
            # Append to CSS file
            if css_file.exists():
                with open(css_file, 'a') as f:
                    f.write(new_styles)
            else:
                with open(css_file, 'w') as f:
                    f.write(new_styles)
            
            logger.info(f"Updated styles in {css_file}")
            return f"Updated CSS styles for {task['title']}"
            
        except Exception as e:
            logger.error(f"Error updating styles: {e}")
            return f"Error updating styles: {e}"
    
    async def add_component(self, task: Dict[str, Any], plan: str) -> str:
        """Add a new React component"""
        try:
            # Create a simple component based on the task
            task_lower = task['title'].lower()
            component_name = "GeneratedComponent"
            
            if "button" in task_lower:
                component_name = "CustomButton"
                component_code = """import React from 'react';

interface CustomButtonProps {
  onClick?: () => void;
  children: React.ReactNode;
  className?: string;
}

export const CustomButton: React.FC<CustomButtonProps> = ({ onClick, children, className = '' }) => {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 ${className}`}
    >
      {children}
    </button>
  );
};"""
            else:
                # Generic component
                component_code = f"""import React from 'react';

interface {component_name}Props {{
  title?: string;
  description?: string;
}}

export const {component_name}: React.FC<{component_name}Props> = ({{ 
  title = "{task['title']}", 
  description = "{task.get('description', 'Auto-generated component')}"
}}) => {{
  return (
    <div className="p-4 m-2 border border-gray-300 rounded">
      <h3 className="text-lg font-semibold">{{title}}</h3>
      <p className="text-gray-600">{{description}}</p>
    </div>
  );
}};"""
            
            # Write component file
            component_file = self.project_path / "src" / "components" / f"{component_name}.tsx"
            component_file.parent.mkdir(exist_ok=True)
            
            with open(component_file, 'w') as f:
                f.write(component_code)
            
            logger.info(f"Created component {component_name} in {component_file}")
            return f"Created {component_name} component"
            
        except Exception as e:
            logger.error(f"Error adding component: {e}")
            return f"Error adding component: {e}"
    
    async def create_task_documentation(self, task: Dict[str, Any], plan: str) -> str:
        """Create documentation for the task"""
        try:
            doc_content = f"""# Task Implementation: {task['title']}

## Task Details
- **ID**: {task.get('id', 'Unknown')}
- **Title**: {task['title']}
- **Description**: {task.get('description', 'No description')}
- **Status**: Implemented

## Implementation Plan
{plan}

## Generated At
{datetime.now().isoformat()}

## Notes
This task was implemented using the Claude Code Automation system.
"""
            
            # Create documentation file
            doc_file = self.project_path / f"task_{task.get('id', 'unknown')[:8]}_implementation.md"
            with open(doc_file, 'w') as f:
                f.write(doc_content)
            
            logger.info(f"Created documentation: {doc_file}")
            return f"Created task documentation"
            
        except Exception as e:
            logger.error(f"Error creating documentation: {e}")
            return f"Error creating documentation: {e}"
    
    async def rebuild_frontend(self) -> str:
        """Rebuild the frontend"""
        try:
            import subprocess
            
            result = subprocess.run(
                ["npm", "run", "build"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                logger.info("Frontend rebuilt successfully")
                return "success"
            else:
                logger.error(f"Frontend build failed: {result.stderr}")
                return f"failed: {result.stderr}"
                
        except Exception as e:
            logger.error(f"Error rebuilding frontend: {e}")
            return f"error: {e}"
    
    async def get_project_context_with_cli(self) -> str:
        """Get project context using command line tools"""
        context_parts = []
        
        try:
            import subprocess
            
            # Get project structure
            result = subprocess.run(
                ["ls", "-la"], 
                cwd=self.project_path, 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            if result.returncode == 0:
                context_parts.append(f"=== Project Root (ls -la) ===\n{result.stdout}")
            
            # Get src directory structure  
            result = subprocess.run(
                ["find", "src", "-type", "f", "-name", "*.tsx", "-o", "-name", "*.ts", "-o", "-name", "*.css"], 
                cwd=self.project_path, 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            if result.returncode == 0:
                context_parts.append(f"=== Frontend Files (find src) ===\n{result.stdout}")
            
            # Get current HTML title
            result = subprocess.run(
                ["grep", "-n", "<title>", "public/index.html"], 
                cwd=self.project_path, 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            if result.returncode == 0:
                context_parts.append(f"=== Current HTML Title ===\n{result.stdout}")
            
            # Get current CSS content (first 20 lines)
            result = subprocess.run(
                ["head", "-20", "src/index.css"], 
                cwd=self.project_path, 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            if result.returncode == 0:
                context_parts.append(f"=== Current CSS (head -20 src/index.css) ===\n{result.stdout}")
            
            # Check if package.json exists
            result = subprocess.run(
                ["cat", "package.json"], 
                cwd=self.project_path, 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            if result.returncode == 0:
                # Just get the name and scripts section
                lines = result.stdout.split('\n')
                relevant_lines = [line for line in lines[:15] if 'name' in line or 'scripts' in line or '"' in line]
                context_parts.append(f"=== Package Info ===\n" + '\n'.join(relevant_lines[:10]))
            
            return "\n\n".join(context_parts)
            
        except Exception as e:
            logger.error(f"Error getting project context with CLI: {e}")
            return f"Error running CLI commands: {e}"
    
    async def run_tests(self) -> Dict[str, Any]:
        """Run the testing framework"""
        logger.info("Running tests...")
        
        if self.simulation_mode:
            logger.info("Running in simulation mode - simulating test execution")
            return {
                "status": "simulated_tests",
                "output": "All simulated tests passed successfully",
                "all_passed": True,
                "errors": None
            }
        
        test_prompt = """
        Please run the complete test suite for this project:
        1. Run unit tests
        2. Run integration tests
        3. Run end-to-end tests (avoid using mock data)
        4. Report any failures with detailed error messages
        5. Ensure all tests pass before proceeding
        
        If tests fail, analyze the failures and fix them automatically.
        """
        
        try:
            # Use Claude Code to run tests
            process = await asyncio.create_subprocess_exec(
                self.claude_code_cmd,
                cwd=self.project_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate(test_prompt.encode())
            
            return {
                "status": "completed",
                "output": stdout.decode(),
                "all_passed": process.returncode == 0,
                "errors": stderr.decode() if stderr else None
            }
        except Exception as e:
            logger.error(f"Error during testing: {e}")
            return {
                "status": "test_error",
                "output": str(e),
                "all_passed": False,
                "errors": str(e)
            }
    
    async def debug_and_fix(self, test_results: Dict[str, Any]) -> Dict[str, Any]:
        """Debug and fix any test failures"""
        if test_results["all_passed"]:
            return {"status": "no_fixes_needed", "success": True}
        
        logger.info("Tests failed, debugging and fixing...")
        
        if self.simulation_mode:
            logger.info("Running in simulation mode - simulating debug and fix")
            return {
                "status": "simulated_fixes",
                "output": "Simulated debugging and fixing completed",
                "success": True
            }
        
        debug_prompt = f"""
        The tests failed with the following results:
        {test_results['output']}
        
        Errors:
        {test_results.get('errors', 'No error details')}
        
        Please:
        1. Analyze the test failures
        2. Identify the root cause
        3. Fix the implementation
        4. Re-run the tests
        5. Repeat until all tests pass
        
        Do not use mock data for end-to-end tests - ensure real functionality works.
        """
        
        try:
            process = await asyncio.create_subprocess_exec(
                self.claude_code_cmd,
                cwd=self.project_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate(debug_prompt.encode())
            
            return {
                "status": "fixed",
                "output": stdout.decode(),
                "success": process.returncode == 0
            }
        except Exception as e:
            logger.error(f"Error during debug and fix: {e}")
            return {
                "status": "debug_error",
                "output": str(e),
                "success": False
            }
    
    async def final_review(self) -> Dict[str, Any]:
        """Perform final code review"""
        logger.info("Performing final code review...")
        
        if self.simulation_mode:
            logger.info("Running in simulation mode - simulating final review")
            return {
                "status": "simulated_review",
                "review_summary": "Simulated comprehensive code review completed successfully",
                "approved": True
            }
        
        review_prompt = """
        Please perform a comprehensive final review of the implementation:
        1. Code quality and best practices
        2. Test coverage
        3. Documentation completeness
        4. Performance considerations
        5. Security implications
        6. Adherence to project conventions
        
        Provide a summary of the implementation and any recommendations.
        """
        
        try:
            process = await asyncio.create_subprocess_exec(
                self.claude_code_cmd,
                cwd=self.project_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate(review_prompt.encode())
            
            return {
                "status": "reviewed",
                "review_summary": stdout.decode(),
                "approved": process.returncode == 0
            }
        except Exception as e:
            logger.error(f"Error during final review: {e}")
            return {
                "status": "review_error",
                "review_summary": str(e),
                "approved": False
            }
    
    async def commit_and_push(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Commit and push changes"""
        logger.info("Committing and pushing changes...")
        
        if self.simulation_mode:
            logger.info("Running in simulation mode - simulating commit and push")
            return {
                "status": "simulated_commit",
                "commit_info": f"Simulated commit and push for task: {task['title']}",
                "success": True
            }
        
        commit_prompt = f"""
        Please commit and push the changes for this task:
        Task: {task['title']}
        
        1. Stage all relevant changes
        2. Create a meaningful commit message
        3. Push to the appropriate branch
        4. Provide a summary of what was committed
        """
        
        try:
            process = await asyncio.create_subprocess_exec(
                self.claude_code_cmd,
                cwd=self.project_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate(commit_prompt.encode())
            
            return {
                "status": "committed",
                "commit_info": stdout.decode(),
                "success": process.returncode == 0
            }
        except Exception as e:
            logger.error(f"Error during commit and push: {e}")
            return {
                "status": "commit_error",
                "commit_info": str(e),
                "success": False
            }
    
    async def update_archon_task(self, task: Dict[str, Any], status: str) -> Dict[str, Any]:
        """Update task status in Archon"""
        logger.info(f"Updating Archon task {task['task_id']} to status: {status}")
        
        # This would use the Archon MCP server when available
        update_prompt = f"""
        Please update the task in Archon:
        Task ID: {task['task_id']}
        New Status: {status}
        
        Include any relevant completion notes or next steps.
        """
        
        # Placeholder for Archon MCP integration
        return {
            "status": "updated",
            "task_id": task["task_id"],
            "new_status": status
        }
    
    async def run_complete_cycle(self, task_id: Optional[str] = None) -> Dict[str, Any]:
        """Run the complete automated development cycle"""
        logger.info("Starting complete automated development cycle...")
        start_time = datetime.now()
        task = None
        
        try:
            # Initialize
            logger.debug("Initializing automation system...")
            await self.initialize()
            logger.info(f"Initialization completed. Simulation mode: {self.simulation_mode}")
            
            # Get task from API server
            logger.debug(f"Retrieving task with ID: {task_id}")
            task = await self.get_archon_task(task_id)
            if not task:
                logger.info("No tasks available, skipping cycle")
                return {
                    "status": "no_tasks",
                    "message": "No pending tasks available",
                    "duration": "0:00:00.000001"
                }
            logger.info(f"Working on task: {task['title']} (ID: {task['id']})")
            
            # Implement with Claude Code
            logger.debug("Starting implementation phase...")
            impl_result = await self.claude_code_implement(task)
            logger.info(f"Implementation completed with status: {impl_result['status']}")
            
            # Test and iterate until all tests pass
            max_iterations = 5
            iteration = 0
            test_results = None
            
            logger.debug(f"Starting test iterations (max: {max_iterations})...")
            while iteration < max_iterations:
                logger.debug(f"Running test iteration {iteration + 1}")
                test_results = await self.run_tests()
                
                if test_results["all_passed"]:
                    logger.info(f"All tests passed on iteration {iteration + 1}!")
                    break
                
                logger.warning(f"Tests failed on iteration {iteration + 1}/{max_iterations}")
                logger.debug(f"Test failure details: {test_results.get('errors', 'No details')}")
                
                fix_result = await self.debug_and_fix(test_results)
                
                if not fix_result.get("success", False):
                    logger.error("Failed to fix test failures")
                    raise RuntimeError("Failed to fix test failures")
                
                iteration += 1
            
            if iteration >= max_iterations:
                error_msg = f"Max iterations ({max_iterations}) reached, tests still failing"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            # Final review
            logger.debug("Starting final review...")
            review_result = await self.final_review()
            if not review_result["approved"]:
                logger.warning("Final review found issues, but proceeding...")
            else:
                logger.info("Final review approved")
            
            # Commit and push
            logger.debug("Starting commit and push...")
            commit_result = await self.commit_and_push(task)
            if not commit_result["success"]:
                logger.error("Failed to commit and push changes")
                raise RuntimeError("Failed to commit and push changes")
            logger.info("Changes committed and pushed successfully")
            
            # Update task status to completed
            logger.debug("Updating task status to completed...")
            try:
                import requests
                requests.patch(f'http://localhost:8009/api/tasks/{task["id"]}', 
                             json={'status': 'completed'})
                logger.info("Task status updated to completed")
            except Exception as e:
                logger.error(f"Failed to update task status: {e}")
            
            update_result = {"status": "updated", "task_id": task["id"], "new_status": "completed"}
            
            duration = datetime.now() - start_time
            logger.info(f"Complete cycle finished successfully in {duration}")
            
            return {
                "status": "success",
                "task": task,
                "implementation": impl_result,
                "tests_passed": True,
                "review": review_result,
                "committed": commit_result,
                "archon_updated": update_result,
                "duration": str(duration),
                "iterations": iteration + 1
            }
            
        except Exception as e:
            duration = datetime.now() - start_time
            error_details = {
                "error": str(e),
                "type": type(e).__name__,
                "traceback": traceback.format_exc()
            }
            
            logger.error(f"Cycle failed after {duration}: {e}")
            logger.debug(f"Full error traceback:\n{error_details['traceback']}")
            
            return {
                "status": "error",
                "error_details": error_details,
                "task": task,
                "duration": str(duration)
            }
    
    async def run_continuous_loop(self):
        """Run continuous loop processing tasks from Archon"""
        logger.info("Starting continuous automation loop...")
        loop_count = 0
        
        while True:
            loop_count += 1
            logger.debug(f"Starting loop iteration {loop_count}")
            
            try:
                result = await self.run_complete_cycle()
                
                if result["status"] == "success":
                    logger.info(f"Task completed successfully: {result['task']['title']} "
                              f"(Duration: {result['duration']}, Iterations: {result['iterations']})")
                elif result["status"] == "no_tasks":
                    logger.debug("No tasks available, waiting...")
                else:
                    logger.error(f"Task failed: {result.get('error_details', {}).get('error', 'Unknown error')}")
                    if "error_details" in result:
                        logger.debug(f"Error details: {result['error_details']}")
                
                # Wait before checking for next task
                logger.debug("Waiting 10 seconds before next cycle...")
                await asyncio.sleep(10)
                
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt - stopping automation loop...")
                break
            except Exception as e:
                logger.error(f"Unexpected error in continuous loop iteration {loop_count}: {e}")
                logger.debug(f"Loop error traceback:\n{traceback.format_exc()}")
                logger.info("Waiting 30 seconds before retry...")
                await asyncio.sleep(30)  # Wait before retrying
        
        logger.info(f"Automation loop stopped after {loop_count} iterations")


async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Automated Development Workflow")
    parser.add_argument("--project-path", required=True, help="Path to the project directory")
    parser.add_argument("--task-id", help="Specific task ID to process")
    parser.add_argument("--continuous", action="store_true", help="Run in continuous mode")
    
    args = parser.parse_args()
    
    automation = ClaudeCodeAutomation(args.project_path)
    
    if args.continuous:
        await automation.run_continuous_loop()
    else:
        result = await automation.run_complete_cycle(args.task_id)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())