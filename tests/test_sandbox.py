"""Integration tests for Docker Sandbox runner."""

import pytest
from sandbox.docker_runner import DockerSandbox
from schemas.models import FailureCategory
from evaluation.evaluator import TestEvaluator


def test_sandbox_docker_availability_detection():
    sandbox = DockerSandbox()
    available = sandbox.is_docker_available()
    assert isinstance(available, bool)


def test_sandbox_refuses_when_docker_unavailable(monkeypatch):
    sandbox = DockerSandbox()
    # Force docker unavailable check
    monkeypatch.setattr(sandbox, "is_docker_available", lambda: False)

    res = sandbox.execute_test_suite("def solve(): pass", "def test_ok(): pass")
    assert res.sandbox_available is False
    assert res.exit_code == -1
    assert "Secure Docker execution is unavailable" in res.error_message

    eval_res = TestEvaluator.parse_and_classify(res)
    assert eval_res.primary_failure_category == FailureCategory.SANDBOX_ERROR
    assert eval_res.all_passed is False


@pytest.mark.skipif(not DockerSandbox().is_docker_available(), reason="Docker daemon not running on host")
def test_live_docker_sandbox_execution():
    """Live sandbox execution test when Docker is active on host."""
    sandbox = DockerSandbox(timeout_seconds=10)
    solution = "def add(a: int, b: int) -> int:\n    return a + b\n"
    test_code = (
        "import pytest\n"
        "from solution import add\n\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n"
    )
    result = sandbox.execute_test_suite(solution, test_code)
    assert result.sandbox_available is True
    assert result.exit_code == 0
    assert result.timed_out is False

    eval_res = TestEvaluator.parse_and_classify(result)
    assert eval_res.all_passed is True
    assert eval_res.passed_tests == 1
