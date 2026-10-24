"""Unit tests for Pydantic schemas, validation, and error boundaries."""

import pytest
from pydantic import ValidationError
from schemas.models import (
    FailureCategory,
    TaskCreateRequest,
    TaskStatus,
    TestCaseResult,
    SandboxExecutionResult,
    TestSuiteEvaluation,
)


def test_task_create_request_valid():
    req = TaskCreateRequest(
        prompt="Write a binary search function.",
        requirements="Must run in O(log n) time.",
        language="python",
        max_repair_attempts=4,
    )
    assert req.prompt == "Write a binary search function."
    assert req.max_repair_attempts == 4


def test_task_create_request_validation_failure():
    # Prompt too short
    with pytest.raises(ValidationError):
        TaskCreateRequest(prompt="abc")

    # Repair attempts exceeds maximum allowed
    with pytest.raises(ValidationError):
        TaskCreateRequest(prompt="Valid task prompt description", max_repair_attempts=20)


def test_test_case_result_defaults():
    res = TestCaseResult(name="test_addition", passed=True)
    assert res.passed is True
    assert res.failure_category == FailureCategory.NONE
    assert res.execution_time_ms == 0.0


def test_sandbox_execution_result_defaults():
    res = SandboxExecutionResult(stdout="hello", stderr="", exit_code=0)
    assert res.timed_out is False
    assert res.sandbox_available is True
