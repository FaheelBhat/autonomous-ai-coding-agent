"""Autonomous coding agent orchestrator with test-driven self-repair loop."""

import logging
import uuid
from datetime import datetime
from typing import List, Optional, Tuple
from database.db import DatabaseManager
from evaluation.evaluator import TestEvaluator
from llm.provider import BaseLLMProvider, get_llm_provider
from sandbox.docker_runner import DockerSandbox
from schemas.models import (
    ExecutionReport,
    RepairIteration,
    TaskCreateRequest,
    TaskStatus,
)

logger = logging.getLogger(__name__)


class CodingAgent:
    """Orchestrates code generation, isolated test execution, and iterative repair."""

    def __init__(
        self,
        llm_provider: Optional[BaseLLMProvider] = None,
        sandbox: Optional[DockerSandbox] = None,
        db_manager: Optional[DatabaseManager] = None,
    ):
        self.llm = llm_provider or get_llm_provider()
        self.sandbox = sandbox or DockerSandbox()
        self.db = db_manager or DatabaseManager()

    def run_task(self, request: TaskCreateRequest, task_id: Optional[str] = None) -> ExecutionReport:
        """Execute end-to-end autonomous agent workflow."""
        task_id = task_id or str(uuid.uuid4())
        created_at = datetime.utcnow()

        logger.info("Starting autonomous agent workflow for task: %s", task_id)
        self.db.create_task(
            task_id=task_id,
            prompt=request.prompt,
            requirements=request.requirements,
            language=request.language,
            max_repair_attempts=request.max_repair_attempts,
        )

        try:
            # 1. Analyze and generate initial implementation
            self.db.update_task_status(task_id, TaskStatus.GENERATING)
            initial_code, explanation = self._generate_solution(
                request.prompt, request.requirements
            )

            # 2. Generate robust unit tests
            self.db.update_task_status(task_id, TaskStatus.TESTING)
            test_code = self._generate_tests(
                request.prompt, request.requirements, initial_code
            )

            current_code = initial_code
            current_explanation = explanation
            repair_history: List[RepairIteration] = []
            remaining_errors: List[str] = []

            # 3. Initial execution and testing
            sandbox_res = self.sandbox.execute_test_suite(current_code, test_code)
            evaluation = TestEvaluator.parse_and_classify(sandbox_res)

            # Record initial test state
            repair_history.append(
                RepairIteration(
                    iteration_number=0,
                    attempted_code=current_code,
                    explanation=current_explanation,
                    test_evaluation=evaluation,
                    feedback_provided="Initial solution generation",
                )
            )

            # 4. Self-repair loop if tests fail
            repair_attempts_used = 0
            while not evaluation.all_passed and repair_attempts_used < request.max_repair_attempts:
                repair_attempts_used += 1
                self.db.update_task_status(task_id, TaskStatus.REPAIRING)
                logger.info(
                    "Task %s: Attempting self-repair iteration %d/%d",
                    task_id,
                    repair_attempts_used,
                    request.max_repair_attempts,
                )

                feedback_msg = evaluation.feedback_summary
                repaired_code, repair_exp = self._repair_solution(
                    task=request.prompt,
                    requirements=request.requirements,
                    failing_code=current_code,
                    test_code=test_code,
                    feedback=feedback_msg,
                )

                current_code = repaired_code
                current_explanation = repair_exp

                # Run tests on repaired candidate
                sandbox_res = self.sandbox.execute_test_suite(current_code, test_code)
                evaluation = TestEvaluator.parse_and_classify(sandbox_res)

                repair_history.append(
                    RepairIteration(
                        iteration_number=repair_attempts_used,
                        attempted_code=current_code,
                        explanation=current_explanation,
                        test_evaluation=evaluation,
                        feedback_provided=feedback_msg,
                    )
                )

            # Determine final status and limitations
            completed_at = datetime.utcnow()
            known_limitations: List[str] = []

            if not sandbox_res.sandbox_available:
                final_status = TaskStatus.FAILED
                remaining_errors.append("Secure Docker execution unavailable.")
                known_limitations.append(
                    "Docker sandbox environment was not available on the execution host."
                )
            elif evaluation.all_passed:
                final_status = TaskStatus.COMPLETED
            else:
                final_status = TaskStatus.FAILED
                remaining_errors.append(
                    f"Tests did not pass within {request.max_repair_attempts} repair attempts. "
                    f"Last failure: {evaluation.primary_failure_category.value}"
                )
                known_limitations.append(
                    "Algorithmic complexity or edge cases required further iterations than allowed quota."
                )

            report = ExecutionReport(
                task_id=task_id,
                original_task=request.prompt,
                requirements=request.requirements,
                final_code=current_code,
                brief_explanation=current_explanation,
                generated_tests=test_code,
                repair_attempts_used=repair_attempts_used,
                max_repair_attempts=request.max_repair_attempts,
                final_status=final_status,
                all_tests_passed=evaluation.all_passed,
                test_summary={
                    "total_tests": evaluation.total_tests,
                    "passed_tests": evaluation.passed_tests,
                    "failed_tests": evaluation.failed_tests,
                    "duration_ms": evaluation.execution_duration_ms,
                    "primary_failure": evaluation.primary_failure_category.value,
                },
                repair_history=repair_history,
                remaining_errors=remaining_errors,
                known_limitations=known_limitations,
                created_at=created_at,
                completed_at=completed_at,
            )

            # Persist report
            self.db.save_execution_report(task_id, report)
            logger.info("Task %s completed with status %s", task_id, final_status.value)
            return report

        except Exception as e:
            logger.error("Agent workflow error on task %s: %s", task_id, str(e), exc_info=True)
            self.db.update_task_status(task_id, TaskStatus.FAILED, error=str(e))
            raise

    def _generate_solution(self, prompt: str, requirements: Optional[str]) -> Tuple[str, str]:
        """Ask LLM to generate Python implementation and short explanation."""
        system_prompt = (
            "You are an expert senior software engineer. Write clean, idiomatic, and correct Python 3 code. "
            "Return your code enclosed in a ```python ... ``` markdown block. "
            "Before the code block, provide a brief (1-3 sentence) explanation of your approach. "
            "Do not include test execution or asserts in the solution code itself."
        )

        user_content = f"Programming Problem:\n{prompt}\n"
        if requirements:
            user_content += f"\nSpecific Constraints and Requirements:\n{requirements}\n"

        resp = self.llm.generate(prompt=user_content, system_prompt=system_prompt)
        code = resp.extract_python_code()

        # Extract brief explanation from non-code text
        explanation_lines = []
        for line in resp.content.splitlines():
            if line.strip().startswith("```"):
                break
            if line.strip():
                explanation_lines.append(line.strip())
        explanation = " ".join(explanation_lines) or "Solution implemented using standard algorithms."

        return code, explanation

    def _generate_tests(self, prompt: str, requirements: Optional[str], solution_code: str) -> str:
        """Ask LLM to generate automated pytest test cases."""
        system_prompt = (
            "You are a Quality Assurance and Software Testing specialist. "
            "Write a thorough suite of automated tests using pytest for the given Python problem. "
            "Your tests MUST import functions/classes directly from `solution` (e.g. `from solution import ...`). "
            "Cover basic cases, edge cases (empty inputs, negatives, boundaries), and large inputs if applicable. "
            "Return ONLY the test code in a ```python ... ``` block."
        )

        user_content = (
            f"Programming Task:\n{prompt}\n"
            f"Requirements:\n{requirements or 'None'}\n\n"
            f"Candidate Implementation:\n```python\n{solution_code}\n```\n\n"
            "Generate comprehensive pytest unit tests."
        )

        resp = self.llm.generate(prompt=user_content, system_prompt=system_prompt)
        test_code = resp.extract_python_code()
        return test_code

    def _repair_solution(
        self,
        task: str,
        requirements: Optional[str],
        failing_code: str,
        test_code: str,
        feedback: str,
    ) -> Tuple[str, str]:
        """Ask LLM to inspect failures and provide repaired Python code."""
        system_prompt = (
            "You are an expert debugger and senior Python developer. "
            "Your previous code failed automated tests. Analyze the test failure traceback, "
            "identify the root cause bug, and generate a fixed, fully working Python implementation. "
            "Return your fixed code in a ```python ... ``` block with a brief 1-2 sentence description of what was fixed."
        )

        user_content = (
            f"Original Task:\n{task}\n"
            f"Requirements:\n{requirements or 'None'}\n\n"
            f"Current Implementation:\n```python\n{failing_code}\n```\n\n"
            f"Test Suite:\n```python\n{test_code}\n```\n\n"
            f"Test Execution Feedback & Traceback:\n{feedback}\n\n"
            "Please fix the implementation to make all tests pass."
        )

        resp = self.llm.generate(prompt=user_content, system_prompt=system_prompt)
        repaired_code = resp.extract_python_code()

        explanation_lines = []
        for line in resp.content.splitlines():
            if line.strip().startswith("```"):
                break
            if line.strip():
                explanation_lines.append(line.strip())
        explanation = " ".join(explanation_lines) or "Refactored implementation to satisfy test assertions."

        return repaired_code, explanation
