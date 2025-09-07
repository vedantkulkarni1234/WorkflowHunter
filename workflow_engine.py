"""
Workflow execution engine for the Workflow Generator application.
Contains the VariableResolver and WorkflowRunner classes.
"""

import os
import subprocess
import time
import logging
import shutil
import queue
import threading
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, wait

from models import WorkflowStep, Workflow, ExecutionResult, StepStatus, ExecutionMode

logger = logging.getLogger(__name__)


class VariableResolver:
    """Handles variable substitution in commands and paths."""
    
    def __init__(self, global_vars: Dict[str, str], step_vars: Dict[str, str], 
                 execution_results: Optional[Dict[str, ExecutionResult]] = None, 
                 workflow_steps: Optional[List[WorkflowStep]] = None):
        self.variables = {**global_vars, **step_vars}
        self.execution_results = execution_results or {}
        self.workflow_steps = workflow_steps or []
        self.step_id_to_name = {step.id: step.name for step in self.workflow_steps}
        self.step_name_to_id = {step.name: step.id for step in self.workflow_steps}
    
    def resolve(self, text: str, current_step_id: Optional[str] = None) -> str:
        """Replace variables in text with their values."""
        resolved = text
        
        # Handle special variables like {previous_step.exit_code}
        import re
        special_vars = re.findall(r'\{([^}]+)\}', text)
        
        for var in special_vars:
            if '.' in var and var not in self.variables:
                parts = var.split('.', 1)
                step_ref = parts[0]
                property_name = parts[1]
                
                # Handle previous_step reference
                if step_ref == "previous_step" and current_step_id and self.workflow_steps:
                    # Find the previous step in the workflow
                    step_ids = [step.id for step in self.workflow_steps]
                    if current_step_id in step_ids:
                        current_index = step_ids.index(current_step_id)
                        if current_index > 0:
                            previous_step_id = step_ids[current_index - 1]
                            if previous_step_id in self.execution_results:
                                result = self.execution_results[previous_step_id]
                                if property_name == "exit_code":
                                    resolved = resolved.replace(f"{{{var}}}", str(result.exit_code))
                                elif property_name == "findings_count":
                                    # For findings_count, we would need to parse the output
                                    # For now, we'll just count lines as a simple approximation
                                    findings_count = len(result.stdout.split('\n')) if result.stdout else 0
                                    resolved = resolved.replace(f"{{{var}}}", str(findings_count))
                                elif property_name == "status":
                                    resolved = resolved.replace(f"{{{var}}}", result.status.value)
                                    
                # Handle step_name.property reference
                if step_ref in self.step_name_to_id:
                    step_id = self.step_name_to_id[step_ref]
                    if step_id in self.execution_results:
                        result = self.execution_results[step_id]
                        if property_name == "exit_code":
                            resolved = resolved.replace(f"{{{var}}}", str(result.exit_code))
                        elif property_name == "findings_count":
                            # For findings_count, we would need to parse the output
                            # For now, we'll just count lines as a simple approximation
                            findings_count = len(result.stdout.split('\n')) if result.stdout else 0
                            resolved = resolved.replace(f"{{{var}}}", str(findings_count))
                        elif property_name == "status":
                            resolved = resolved.replace(f"{{{var}}}", result.status.value)
                            
        # Handle regular variables
        for key, value in self.variables.items():
            resolved = resolved.replace(f"{{{key}}}", str(value))
        return resolved
    
    def validate_variables(self, text: str) -> List[str]:
        """Find unresolved variables in text."""
        import re
        unresolved = re.findall(r'\{([^}]+)\}', text)
        return [var for var in unresolved if var not in self.variables]


class WorkflowRunner:
    """Executes workflows with proper isolation and monitoring."""
    
    def __init__(self, dry_run: bool = False, sandbox_dir: Optional[str] = None):
        self.dry_run = dry_run
        self.sandbox_dir = sandbox_dir or "/tmp/workflow_sandbox"
        self.running = False
        self.current_execution = None
        self.execution_queue = queue.Queue()
        self.results: Dict[str, ExecutionResult] = {}
        self.status_callback: Optional[Callable] = None
        self.animation_callback: Optional[Callable] = None  # For particle animation updates
    
    def evaluate_condition(self, step: WorkflowStep, resolver: VariableResolver) -> bool:
        """Evaluate conditional execution logic for a step."""
        # If no condition, always execute
        if step.condition_type == "none" or not step.condition_expression:
            return True
            
        try:
            # Resolve variables in the condition expression
            resolved_expression = resolver.resolve(step.condition_expression, step.id)
            
            # Simple evaluation of condition expression
            # This supports basic comparisons like:
            # {previous_step.exit_code} == 0
            # {previous_step.findings_count} > 5
            # {step_name.exit_code} != 0
            
            # For now, we'll do simple evaluation using Python's eval
            # In a production environment, you might want a safer expression evaluator
            # We need to parse the resolved expression to extract values for comparison
            # For example: "0 == 0" where the first 0 came from {previous_step.exit_code}
            
            # Simple approach: if the resolved expression contains "True" or "False"
            if "True" in resolved_expression and "False" not in resolved_expression:
                result = True
            elif "False" in resolved_expression and "True" not in resolved_expression:
                result = False
            else:
                # Try to evaluate as a boolean expression
                result = eval(resolved_expression, {"__builtins__": {}}, {})
            return result if step.condition_type == "if" else not result
        except Exception as e:
            logger.warning(f"Condition evaluation failed for step {step.name}: {e}")
            # If condition evaluation fails, we skip the step
            return False
        
    def set_status_callback(self, callback: Callable):
        """Set callback for status updates."""
        self.status_callback = callback
    
    def set_animation_callback(self, callback: Callable):
        """Set callback for animation updates."""
        self.animation_callback = callback
    
    def execute_workflow(self, workflow: Workflow, global_vars: Dict[str, str], step_vars: Dict[str, str]) -> Dict[str, ExecutionResult]:
        """Execute a complete workflow."""
        self.results = {}
        self.running = True
        
        try:
            self._prepare_sandbox()
            resolver = VariableResolver(global_vars, step_vars, self.results, workflow.steps)
            
            if workflow.execution_mode == ExecutionMode.SEQUENTIAL:
                self._execute_sequential(workflow, resolver)
            else:
                self._execute_parallel(workflow, resolver)
                
        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            if self.status_callback:
                self.status_callback(None, None, f"Workflow failed: {e}")
        finally:
            self.running = False
            
        return self.results
    
    def _prepare_sandbox(self):
        """Prepare isolated execution environment."""
        sandbox_path = Path(self.sandbox_dir)
        sandbox_path.mkdir(parents=True, exist_ok=True)
        os.chmod(self.sandbox_dir, 0o700)
    
    def _skip_step(self, step: WorkflowStep, message: str):
        """Skip a step and record the reason."""
        result = ExecutionResult(
            step_id=step.id,
            status=StepStatus.SKIPPED,
            start_time=datetime.now().isoformat(),
            error_message=message
        )
        self.results[step.id] = result
        if self.status_callback:
            self.status_callback(step.id, StepStatus.SKIPPED, message)

    def _execute_sequential(self, workflow: Workflow, resolver: VariableResolver):
        """Execute steps sequentially."""
        logger.info("Starting sequential execution of workflow.")
        for i, step in enumerate(workflow.steps):
            logger.info(f"Processing step {i+1}/{len(workflow.steps)}: {step.name}")
            if not step.enabled:
                logger.info(f"Step {step.name} is disabled, skipping.")
                continue

            dep_statuses = self._get_dependency_statuses(step.dependencies)
            logger.info(f"Step {step.name} dependencies statuses: {dep_statuses}")

            # Check if dependencies are met
            if all(s == StepStatus.SUCCESS for s in dep_statuses):
                logger.info(f"All dependencies for step {step.name} are met, checking conditions.")
                
                # Check conditional execution
                if self.evaluate_condition(step, resolver):
                    logger.info(f"Condition for step {step.name} is met, executing.")
                    result = self._execute_step(step, resolver)
                    self.results[step.id] = result
                    if result.status == StepStatus.FAILED:
                        logger.error(f"Step {step.name} failed, continuing to next step")
                else:
                    error_message = f"Skipping {step.name}: Condition not met."
                    logger.warning(error_message)
                    self._skip_step(step, error_message)
            else:
                error_message = f"Skipping {step.name}: Dependencies not successfully met."
                logger.warning(error_message)
                self._skip_step(step, error_message)
                continue
        logger.info("Finished sequential execution of workflow.")
    
    def _execute_parallel(self, workflow: Workflow, resolver: VariableResolver):
        """Execute steps in parallel where possible using thread pool and topological sort."""
        logger.info("Starting parallel execution of workflow.")
        
        # Create a mapping of step IDs to steps for easy lookup
        step_map = {step.id: step for step in workflow.steps}
        
        # Build dependency graph and identify initial ready steps
        dependency_graph = {step.id: set(step.dependencies) for step in workflow.steps}
        reverse_dependencies = {step.id: set() for step in workflow.steps}
        
        # Build reverse dependency graph (what steps depend on each step)
        for step in workflow.steps:
            for dep_id in step.dependencies:
                if dep_id in reverse_dependencies:
                    reverse_dependencies[dep_id].add(step.id)
        
        # Find steps with no dependencies (ready to run)
        ready_steps = [step.id for step in workflow.steps if not step.dependencies]
        pending_steps = set(step.id for step in workflow.steps)
        completed_steps = set()
        
        # Thread pool for execution
        max_workers = min(10, len(workflow.steps) or 10)  # Limit concurrent threads
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_step = {}
            
            # Submit initially ready steps
            for step_id in ready_steps:
                if step_id in step_map and step_map[step_id].enabled:
                    # Check conditional execution before submitting
                    if self.evaluate_condition(step_map[step_id], resolver):
                        future = executor.submit(self._execute_step, step_map[step_id], resolver)
                        future_to_step[future] = step_id
                        pending_steps.discard(step_id)
                    else:
                        # Condition not met, skip the step
                        error_message = f"Skipping {step_map[step_id].name}: Condition not met."
                        logger.warning(error_message)
                        self._skip_step(step_map[step_id], error_message)
                        pending_steps.discard(step_id)
                        completed_steps.add(step_id)
            
            # Process completed steps and submit new ready ones
            while future_to_step:
                # Wait for at least one future to complete
                done, _ = wait(future_to_step.keys(), return_when=FIRST_COMPLETED)
                
                # Process completed futures
                for future in done:
                    step_id = future_to_step.pop(future)
                    try:
                        result = future.result()
                        self.results[step_id] = result
                        completed_steps.add(step_id)
                        
                        if self.status_callback:
                            self.status_callback(step_id, result.status, f"Step {step_map[step_id].name} completed with status: {result.status.value}")
                        
                        # Check if any new steps are ready to run
                        newly_ready = []
                        for dependent_id in reverse_dependencies.get(step_id, set()):
                            # Check if all dependencies of this step are completed
                            dep_statuses = self._get_dependency_statuses(step_map[dependent_id].dependencies)
                            if all(s == StepStatus.SUCCESS for s in dep_statuses) and dependent_id in pending_steps:
                                newly_ready.append(dependent_id)
                        
                        # Submit newly ready steps
                        for new_step_id in newly_ready:
                            if step_map[new_step_id].enabled:
                                # Check conditional execution before submitting
                                if self.evaluate_condition(step_map[new_step_id], resolver):
                                    future = executor.submit(self._execute_step, step_map[new_step_id], resolver)
                                    future_to_step[future] = new_step_id
                                    pending_steps.discard(new_step_id)
                                else:
                                    # Condition not met, skip the step
                                    error_message = f"Skipping {step_map[new_step_id].name}: Condition not met."
                                    logger.warning(error_message)
                                    self._skip_step(step_map[new_step_id], error_message)
                                    pending_steps.discard(new_step_id)
                                    completed_steps.add(new_step_id)
                                    
                    except Exception as e:
                        logger.error(f"Error processing step {step_id}: {e}")
                        # Mark step as failed in results
                        if step_id not in self.results:
                            result = ExecutionResult(
                                step_id=step_id,
                                status=StepStatus.FAILED,
                                start_time=datetime.now().isoformat(),
                                error_message=str(e)
                            )
                            self.results[step_id] = result
                            completed_steps.add(step_id)
        
        # Handle any steps that couldn't be executed due to failed dependencies
        for step_id in pending_steps:
            step = step_map[step_id]
            dep_statuses = self._get_dependency_statuses(step.dependencies)
            if not all(s == StepStatus.SUCCESS for s in dep_statuses):
                error_message = f"Skipping {step.name}: Dependencies not successfully met."
                logger.warning(error_message)
                self._skip_step(step, error_message)
        
        logger.info("Finished parallel execution of workflow.")
    
    def _execute_step(self, step: WorkflowStep, resolver: VariableResolver) -> ExecutionResult:
        """Execute a single workflow step."""
        start_time = datetime.now()
        result = ExecutionResult(
            step_id=step.id,
            status=StepStatus.RUNNING,
            start_time=start_time.isoformat()
        )
        
        if self.status_callback:
            self.status_callback(step.id, StepStatus.RUNNING, f"Executing: {step.name}")
        
        # Notify animation system that step is running
        if self.animation_callback:
            self.animation_callback(step.id, "start")
        
        try:
            resolved_command = resolver.resolve(step.command, step.id)
            working_dir = resolver.resolve(step.working_directory, step.id) if step.working_directory else self.sandbox_dir
            
            unresolved = resolver.validate_variables(resolved_command)
            if unresolved:
                raise ValueError(f"Unresolved variables: {unresolved}")

            # Check for command existence
            if resolved_command and not self.dry_run:
                command_name = resolved_command.split()[0]
                if not shutil.which(command_name):
                    raise FileNotFoundError(f"Command '{command_name}' not found in PATH.")
            
            if self.dry_run:
                result.status = StepStatus.SUCCESS
                result.stdout = f"DRY RUN: Would execute: {resolved_command}"
                logger.info(f"DRY RUN: {resolved_command}")
                time.sleep(0.5) # Simulate work
            else:
                process_result = self._run_command(
                    resolved_command, 
                    working_dir, 
                    step.timeout,
                    step.environment_vars
                )
                
                result.stdout = process_result['stdout']
                result.stderr = process_result['stderr']
                result.exit_code = process_result['exit_code']
                result.status = StepStatus.SUCCESS if result.exit_code == 0 else StepStatus.FAILED
                
        except subprocess.TimeoutExpired:
            result.status = StepStatus.TIMEOUT
            result.error_message = f"Step timed out after {step.timeout} seconds"
        except Exception as e:
            result.status = StepStatus.FAILED
            result.error_message = str(e)
        
        end_time = datetime.now()
        result.end_time = end_time.isoformat()
        result.execution_time = (end_time - start_time).total_seconds()
        
        logger.info(f"Step {step.name} completed with status: {result.status.value}")
        if self.status_callback:
            self.status_callback(step.id, result.status, f"Step {step.name} completed with status: {result.status.value}")
        
        # Notify animation system that step has completed
        if self.animation_callback:
            self.animation_callback(step.id, "complete", result.status)
            
        return result
    
    def _run_command(self, command: str, working_dir: str, timeout: int, env_vars: Dict[str, str]) -> Dict[str, Any]:
        """Run a command with proper isolation."""
        env = os.environ.copy()
        env.update(env_vars)
        
        try:
            process = subprocess.run(
                command, shell=True, cwd=working_dir, env=env,
                capture_output=True, text=True, timeout=timeout
            )
            return {'stdout': process.stdout, 'stderr': process.stderr, 'exit_code': process.returncode}
        except subprocess.TimeoutExpired as e:
            stdout = e.stdout.decode() if e.stdout else ""
            stderr = e.stderr.decode() if e.stderr else ""
            return {'stdout': stdout, 'stderr': stderr, 'exit_code': -1}
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return {'stdout': '', 'stderr': str(e), 'exit_code': -1}
    
    def _get_dependency_statuses(self, dependencies: List[str]) -> List[StepStatus]:
        """Get the statuses of all dependency steps."""
        statuses = []
        for dep_id in dependencies:
            if dep_id in self.results:
                statuses.append(self.results[dep_id].status)
            else:
                statuses.append(StepStatus.PENDING) # Dependency hasn't run yet
        return statuses

    
    def abort(self):
        """Abort current execution."""
        self.running = False