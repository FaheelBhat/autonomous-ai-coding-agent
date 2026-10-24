"""Unit tests for evaluation parsing, error classifications, and feedback extraction."""

from evaluation.evaluator import TestEvaluator
from schemas.models import FailureCategory, SandboxExecutionResult


def test_evaluator_sandbox_unavailable():
    sandbox_res = SandboxExecutionResult(
        stdout="",
        stderr="Docker daemon not running",
        exit_code=-1,
        sandbox_available=False,
        error_message="Docker not found",
    )
    eval_res = TestEvaluator.parse_and_classify(sandbox_res)
    assert eval_res.all_passed is False
    assert eval_res.primary_failure_category == FailureCategory.SANDBOX_ERROR
    assert "Docker not found" in eval_res.feedback_summary


def test_evaluator_timeout_classification():
    sandbox_res = SandboxExecutionResult(
        stdout="",
        stderr="Execution timed out after 15 seconds",
        exit_code=-1,
        timed_out=True,
        duration_ms=15000.0,
        sandbox_available=True,
    )
    eval_res = TestEvaluator.parse_and_classify(sandbox_res)
    assert eval_res.all_passed is False
    assert eval_res.primary_failure_category == FailureCategory.TIMEOUT
    assert len(eval_res.test_cases) == 1
    assert eval_res.test_cases[0].failure_category == FailureCategory.TIMEOUT


def test_evaluator_syntax_error():
    syntax_output = (
        '  File "/sandbox/app/solution.py", line 3\n'
        '    def foo(\n'
        '            ^\n'
        'SyntaxError: unexpected EOF while parsing'
    )
    sandbox_res = SandboxExecutionResult(
        stdout="",
        stderr=syntax_output,
        exit_code=1,
        sandbox_available=True,
    )
    eval_res = TestEvaluator.parse_and_classify(sandbox_res)
    assert eval_res.all_passed is False
    assert eval_res.primary_failure_category == FailureCategory.SYNTAX_ERROR
    assert "Syntax/Indentation Error detected" in eval_res.feedback_summary


def test_evaluator_pytest_pass():
    pytest_stdout = (
        "test_solution.py::test_basic PASSED\n"
        "test_solution.py::test_edge PASSED\n"
        "2 passed in 0.05s"
    )
    sandbox_res = SandboxExecutionResult(
        stdout=pytest_stdout,
        stderr="",
        exit_code=0,
        sandbox_available=True,
    )
    eval_res = TestEvaluator.parse_and_classify(sandbox_res)
    assert eval_res.all_passed is True
    assert eval_res.passed_tests == 2
    assert eval_res.failed_tests == 0
    assert eval_res.primary_failure_category == FailureCategory.NONE


def test_evaluator_pytest_assertion_failure():
    pytest_stdout = (
        "test_solution.py::test_basic PASSED\n"
        "test_solution.py::test_fail FAILED\n\n"
        "=================================== FAILURES ===================================\n"
        "__________________________________ test_fail ___________________________________\n"
        "    def test_fail():\n"
        ">       assert solve(10) == 20\n"
        "E       assert 15 == 20\n"
        "=========================== short test summary info ============================\n"
        "1 failed, 1 passed in 0.08s"
    )
    sandbox_res = SandboxExecutionResult(
        stdout=pytest_stdout,
        stderr="",
        exit_code=1,
        sandbox_available=True,
    )
    eval_res = TestEvaluator.parse_and_classify(sandbox_res)
    assert eval_res.all_passed is False
    assert eval_res.passed_tests == 1
    assert eval_res.failed_tests == 1
    assert eval_res.primary_failure_category == FailureCategory.INCORRECT_OUTPUT
    assert "assert 15 == 20" in eval_res.feedback_summary
