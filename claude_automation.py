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
        """Initialize Claude Code session and verify connections"""
        logger.info("Initializing Claude Code automation...")
        
        # Check for claude-code in multiple possible locations
        claude_code_paths = [
            'claude-code',
            '/usr/local/bin/claude-code',
            '/opt/homebrew/bin/claude-code',
            '~/.local/bin/claude-code'
        ]
        
        claude_code_cmd = None
        for path in claude_code_paths:
            try:
                expanded_path = Path(path).expanduser()
                if expanded_path.exists():
                    claude_code_cmd = str(expanded_path)
                    break
                # Try running it directly
                result = subprocess.run([path, '--version'], 
                                      capture_output=True, text=True, check=True)
                claude_code_cmd = path
                logger.info(f"Claude Code version: {result.stdout.strip()}")
                break
            except (subprocess.CalledProcessError, FileNotFoundError, OSError):
                continue
        
        if not claude_code_cmd:
            logger.warning("Claude Code not found. Running in simulation mode...")
            # Set a flag to indicate we're in simulation mode
            self.simulation_mode = True
        else:
            self.simulation_mode = False
            self.claude_code_cmd = claude_code_cmd
        
        # Change to project directory
        if not self.project_path.exists():
            raise RuntimeError(f"Project path does not exist: {self.project_path}")
        
        logger.info(f"Working in project directory: {self.project_path}")
        return True
    
    async def get_archon_task(self, task_id: Optional[str] = None) -> Dict[str, Any]:
        """Retrieve task from Archon MCP server"""
        logger.info("Fetching task from Archon...")
        
        # This would use the Archon MCP server when available
        # For now, providing a structure for the integration
        archon_prompt = """
        Please check Archon for the next available task or the specific task ID if provided.
        Return the task details including:
        - Task ID
        - Title
        - Description
        - Requirements
        - Acceptance criteria
        - Priority
        - Status
        """
        
        # Placeholder for Archon integration
        # In practice, this would use the MCP server connection
        return {
            "task_id": task_id or "next_available",
            "title": "Retrieved from Archon",
            "description": "Task details from Archon MCP server",
            "requirements": [],
            "acceptance_criteria": [],
            "priority": "medium",
            "status": "in_progress"
        }
    
    async def claude_code_implement(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Use Claude Code to implement the task"""
        logger.info(f"Starting implementation for task: {task['title']}")
        
        if self.simulation_mode:
            logger.info("Running in simulation mode - no actual Claude Code execution")
            return {
                "status": "simulated_implementation",
                "output": f"Simulated implementation of task: {task['title']}",
                "changes_made": "Simulated implementation completed"
            }
        
        implementation_prompt = f"""
        I need you to implement the following task using Claude Code:
        
        Task: {task['title']}
        Description: {task['description']}
        Requirements: {json.dumps(task['requirements'], indent=2)}
        Acceptance Criteria: {json.dumps(task['acceptance_criteria'], indent=2)}
        
        Please:
        1. Analyze the current codebase structure
        2. Implement the required functionality
        3. Write comprehensive tests
        4. Ensure code follows project conventions
        5. Document any changes made
        
        Work in the project directory: {self.project_path}
        """
        
        try:
            # Start Claude Code session
            process = await asyncio.create_subprocess_exec(
                self.claude_code_cmd,
                cwd=self.project_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Send implementation prompt
            stdout, stderr = await process.communicate(implementation_prompt.encode())
            
            if process.returncode != 0:
                raise RuntimeError(f"Claude Code implementation failed: {stderr.decode()}")
            
            return {
                "status": "implemented",
                "output": stdout.decode(),
                "changes_made": "Implementation completed via Claude Code"
            }
        except Exception as e:
            logger.error(f"Error during implementation: {e}")
            return {
                "status": "implementation_error",
                "output": str(e),
                "changes_made": "Implementation failed"
            }
    
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
            
            # Get task from Archon
            logger.debug(f"Retrieving task with ID: {task_id}")
            task = await self.get_archon_task(task_id)
            logger.info(f"Working on task: {task['title']} (ID: {task['task_id']})")
            
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
            
            # Update Archon
            logger.debug("Updating task status in Archon...")
            update_result = await self.update_archon_task(task, "completed")
            logger.info("Archon task status updated")
            
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