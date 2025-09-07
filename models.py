"""
Data models for the Workflow Generator application.
Contains Enums, dataclasses, and supporting structures.
"""

import uuid
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Any


class StepStatus(Enum):
    """Enumeration of possible step execution statuses."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"


class ExecutionMode(Enum):
    """Enumeration of workflow execution modes."""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


@dataclass
class WorkflowStep:
    """Represents a single step in a workflow."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    command: str = ""
    working_directory: str = ""
    environment_vars: Dict[str, str] = field(default_factory=dict)
    input_files: List[str] = field(default_factory=list)
    output_files: List[str] = field(default_factory=list)
    timeout: int = 300  # seconds
    retry_count: int = 0
    dependencies: List[str] = field(default_factory=list)  # step IDs
    enabled: bool = True
    step_type: str = "shell"  # shell, python, docker
    custom_script: str = ""
    notes: str = ""
    
    # Conditional execution logic
    condition_type: str = "none"  # none, if, unless
    condition_expression: str = ""  # Expression to evaluate for conditional execution
    
    # Visual layout information
    pos_x: int = 50
    pos_y: int = 50
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the step to a dictionary representation."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkflowStep':
        """Create a WorkflowStep from a dictionary."""
        # Handle condition_type and condition_expression for backward compatibility
        if 'condition_type' not in data:
            data['condition_type'] = 'none'
        if 'condition_expression' not in data:
            data['condition_expression'] = ''
        return cls(**data)


@dataclass 
class Workflow:
    """Represents a complete workflow."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    version: str = "1.0"
    author: str = ""
    tags: List[str] = field(default_factory=list)
    steps: List[WorkflowStep] = field(default_factory=list)
    execution_mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    global_timeout: int = 3600  # seconds
    global_env_vars: Dict[str, str] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    modified_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the workflow to a dictionary representation."""
        data = asdict(self)
        data['execution_mode'] = self.execution_mode.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Workflow':
        """Create a Workflow from a dictionary."""
        if 'execution_mode' in data and isinstance(data['execution_mode'], str):
            try:
                data['execution_mode'] = ExecutionMode(data['execution_mode'])
            except ValueError:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Invalid execution mode '{data['execution_mode']}' in template. Defaulting to sequential.")
                data['execution_mode'] = ExecutionMode.SEQUENTIAL
        steps_data = data.pop('steps', [])
        workflow = cls(**data)
        workflow.steps = [WorkflowStep.from_dict(step) for step in steps_data]
        return workflow


@dataclass
class ExecutionResult:
    """Results from executing a workflow step."""
    step_id: str
    status: StepStatus
    start_time: str
    end_time: str = ""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    execution_time: float = 0.0
    error_message: str = ""


@dataclass
class Particle:
    """Represents a particle in the connection animation."""
    id: str
    x: float
    y: float
    connection_id: str
    progress: float  # 0.0 to 1.0
    speed: float
    color: str
    size: float
    shape: str  # circle, square, diamond
    activity_type: str  # dns, http, file, generic
    particle_type: str = "data"  # data, guidance, highlight


@dataclass
class UserInteraction:
    """Represents a user interaction with the application."""
    timestamp: str
    action: str  # e.g., "step_added", "step_executed", "template_used"
    target: str  # e.g., step name, template name
    context: str  # e.g., "reconnaissance", "exploitation", "reporting"
    duration: float = 0.0  # Optional: time spent on action