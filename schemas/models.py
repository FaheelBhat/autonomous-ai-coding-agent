"""Pydantic schemas for tasks, agent interactions, execution results, and reports."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FailureCategory(str, Enum):
    """Classification of code test and execution failures."""
    SYNTAX_ERROR = "syntax_error"
    RUNTIME_ERROR = "runtime_error"
    INCORRECT_OUTPUT = "incorrect_output"
    TIMEOUT = "timeout"
    SANDBOX_ERROR = "sandbox_error"
    NONE = "none"


class TaskStatus(str, Enum):
    """Lifecycle status of a submitted coding task."""
    PENDING = "pending"
    ANALYZING = "analyzing"
    GENERATING = "generating"
    TESTING = "testing"
    REPAIRING = "repairing"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskCreateRequest(BaseModel):
    """User request to initiate an autonomous coding task."""
    prompt: str = Field(
        ...,
        min_length=5,
        max_length=5000,
        description="The programming problem description in natural language."
    )
    requirements: Optional[str] = Field(
        None,
        max_length=2000,
        description="Specific constraints, edge cases, or complexity requirements."
    )
    language: str = Field(
        default="python",
        description="Target programming language (currently Python 3)."
    )
    max_repair_attempts: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum iterations the agent can perform to self-repair failing code."
    )


class TestCaseResult(BaseModel):
    """Result of an individual test case execution."""
    __test__ = False
    name: str = Field(..., description="Identifier or name of the test.")
    passed: bool = Field(..., description="True if test assertion passed.")
    execution_time_ms: float = Field(default=0.0, description="Duration of test execution in ms.")
    error_message: Optional[str] = Field(None, description="Captured traceback or assertion message.")
    failure_category: FailureCategory = Field(
        default=FailureCategory.NONE,
        description="Categorized classification of the failure."
    )


class SandboxExecutionResult(BaseModel):
    """Raw execution result returned by the secure sandbox runner."""
    stdout: str = Field(default="")
    stderr: str = Field(default="")
    exit_code: int = Field(default=0)
    timed_out: bool = Field(default=false if False else False)
    duration_ms: float = Field(default=0.0)
    sandbox_available: bool = Field(default=True)
    error_message: Optional[str] = Field(None)


class TestSuiteEvaluation(BaseModel):
    """Evaluation summary derived from running tests against the candidate implementation."""
    __test__ = False
    total_tests: int = Field(default=0)
    passed_tests: int = Field(default=0)
    failed_tests: int = Field(default=0)
    all_passed: bool = Field(default=False)
    test_cases: List[TestCaseResult] = Field(default_factory=list)
    primary_failure_category: FailureCategory = Field(default=FailureCategory.NONE)
    feedback_summary: str = Field(default="")
    raw_output: str = Field(default="")
    execution_duration_ms: float = Field(default=0.0)


class RepairIteration(BaseModel):
    """Record of an individual repair cycle in the agent loop."""
    iteration_number: int
    attempted_code: str
    explanation: Optional[str] = None
    test_evaluation: TestSuiteEvaluation
    feedback_provided: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ExecutionReport(BaseModel):
    """Comprehensive structured execution report returned to user/API."""
    task_id: str
    original_task: str
    requirements: Optional[str] = None
    final_code: str
    brief_explanation: str
    generated_tests: str
    repair_attempts_used: int
    max_repair_attempts: int
    final_status: TaskStatus
    all_tests_passed: bool
    test_summary: Dict[str, Any]
    repair_history: List[RepairIteration] = Field(default_factory=list)
    remaining_errors: List[str] = Field(default_factory=list)
    known_limitations: List[str] = Field(default_factory=list)
    created_at: datetime
    completed_at: Optional[datetime] = None


class TaskResponse(BaseModel):
    """API response model for task query operations."""
    task_id: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    report: Optional[ExecutionReport] = None
    error: Optional[str] = None
