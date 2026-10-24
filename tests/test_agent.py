"""Unit tests for the agent orchestrator repair loop with mocked sandbox and LLM."""

import tempfile
from unittest.mock import MagicMock
from agent.orchestrator import CodingAgent
from database.db import DatabaseManager
from llm.provider import MockLLMProvider
from sandbox.docker_runner import DockerSandbox
from schemas.models import (
    SandboxExecutionResult,
    TaskCreateRequest,
    TaskStatus,
)


def test_agent_orchestrator_successful_first_try():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp_db:
        mock_llm = MockLLMProvider()
        mock_sandbox = MagicMock(spec=DockerSandbox)

        # Sandbox passes tests on first run
        mock_sandbox.execute_test_suite.return_value = SandboxExecutionResult(
            stdout="test_solution.py::test_basic PASSED\n1 passed in 0.02s",
            stderr="",
            exit_code=0,
            sandbox_available=True,
        )

        db = DatabaseManager(db_path=tmp_db.name)
        agent = CodingAgent(llm_provider=mock_llm, sandbox=mock_sandbox, db_manager=db)

        req = TaskCreateRequest(
            prompt="Implement addition function",
            max_repair_attempts=3,
        )

        report = agent.run_task(req)
        assert report.final_status == TaskStatus.COMPLETED
        assert report.all_tests_passed is True
        assert report.repair_attempts_used == 0
        assert len(report.repair_history) == 1


def test_agent_orchestrator_repair_loop_success():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp_db:
        mock_llm = MockLLMProvider()
        mock_sandbox = MagicMock(spec=DockerSandbox)

        # First run fails, second run passes after repair
        fail_res = SandboxExecutionResult(
            stdout="test_solution.py::test_basic FAILED\n1 failed in 0.02s\nassert 1 == 2",
            stderr="",
            exit_code=1,
            sandbox_available=True,
        )
        pass_res = SandboxExecutionResult(
            stdout="test_solution.py::test_basic PASSED\n1 passed in 0.02s",
            stderr="",
            exit_code=0,
            sandbox_available=True,
        )
        mock_sandbox.execute_test_suite.side_effect = [fail_res, pass_res]

        db = DatabaseManager(db_path=tmp_db.name)
        agent = CodingAgent(llm_provider=mock_llm, sandbox=mock_sandbox, db_manager=db)

        req = TaskCreateRequest(
            prompt="Implement function that fixes on repair",
            max_repair_attempts=3,
        )

        report = agent.run_task(req)
        assert report.final_status == TaskStatus.COMPLETED
        assert report.all_tests_passed is True
        assert report.repair_attempts_used == 1
        assert len(report.repair_history) == 2


def test_agent_orchestrator_repair_limit_reached():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp_db:
        mock_llm = MockLLMProvider()
        mock_sandbox = MagicMock(spec=DockerSandbox)

        # Persistent failure
        fail_res = SandboxExecutionResult(
            stdout="test_solution.py::test_fail FAILED\n1 failed in 0.02s\nAssertionError",
            stderr="",
            exit_code=1,
            sandbox_available=True,
        )
        mock_sandbox.execute_test_suite.return_value = fail_res

        db = DatabaseManager(db_path=tmp_db.name)
        agent = CodingAgent(llm_provider=mock_llm, sandbox=mock_sandbox, db_manager=db)

        req = TaskCreateRequest(
            prompt="Problem that fails all repairs",
            max_repair_attempts=2,
        )

        report = agent.run_task(req)
        assert report.final_status == TaskStatus.FAILED
        assert report.all_tests_passed is False
        assert report.repair_attempts_used == 2
        assert len(report.remaining_errors) > 0
