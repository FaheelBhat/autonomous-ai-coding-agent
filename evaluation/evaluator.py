"""Test evaluation and error failure classifier."""

import re
from typing import List, Tuple
from schemas.models import (
    FailureCategory,
    SandboxExecutionResult,
    TestCaseResult,
    TestSuiteEvaluation,
)


class TestEvaluator:
    """Parses sandbox outputs, classifies failures, and extracts detailed test case results."""

    @staticmethod
    def parse_and_classify(result: SandboxExecutionResult) -> TestSuiteEvaluation:
        """Analyze SandboxExecutionResult and construct TestSuiteEvaluation."""
        if not result.sandbox_available:
            return TestSuiteEvaluation(
                total_tests=0,
                passed_tests=0,
                failed_tests=0,
                all_passed=False,
                test_cases=[],
                primary_failure_category=FailureCategory.SANDBOX_ERROR,
                feedback_summary=result.error_message or "Sandbox environment is unavailable.",
                raw_output=result.stderr,
                execution_duration_ms=result.duration_ms,
            )

        if result.timed_out:
            return TestSuiteEvaluation(
                total_tests=1,
                passed_tests=0,
                failed_tests=1,
                all_passed=False,
                test_cases=[
                    TestCaseResult(
                        name="ExecutionTimeout",
                        passed=False,
                        execution_time_ms=result.duration_ms,
                        error_message="Execution exceeded allowed time quota.",
                        failure_category=FailureCategory.TIMEOUT,
                    )
                ],
                primary_failure_category=FailureCategory.TIMEOUT,
                feedback_summary=f"Timeout: Execution took > {result.duration_ms}ms and was killed.",
                raw_output=result.stderr or result.stdout,
                execution_duration_ms=result.duration_ms,
            )

        combined_output = (result.stdout + "\n" + result.stderr).strip()

        # Check for SyntaxError / IndentationError
        if "SyntaxError" in combined_output or "IndentationError" in combined_output:
            err_line = TestEvaluator._extract_syntax_error(combined_output)
            return TestSuiteEvaluation(
                total_tests=1,
                passed_tests=0,
                failed_tests=1,
                all_passed=False,
                test_cases=[
                    TestCaseResult(
                        name="SyntaxCheck",
                        passed=False,
                        error_message=err_line,
                        failure_category=FailureCategory.SYNTAX_ERROR,
                    )
                ],
                primary_failure_category=FailureCategory.SYNTAX_ERROR,
                feedback_summary=f"Syntax/Indentation Error detected:\n{err_line}",
                raw_output=combined_output,
                execution_duration_ms=result.duration_ms,
            )

        # Parse pytest output
        test_cases, passed, failed = TestEvaluator._parse_pytest_output(combined_output)
        total = passed + failed
        all_passed = (result.exit_code == 0) and (failed == 0) and (total > 0)

        # Determine primary category
        primary_category = FailureCategory.NONE
        if not all_passed:
            primary_category = TestEvaluator._determine_failure_category(combined_output)

        # Build informative feedback summary for LLM repair
        feedback_summary = TestEvaluator._build_feedback_summary(
            combined_output, test_cases, primary_category
        )

        return TestSuiteEvaluation(
            total_tests=total,
            passed_tests=passed,
            failed_tests=failed,
            all_passed=all_passed,
            test_cases=test_cases,
            primary_failure_category=primary_category,
            feedback_summary=feedback_summary,
            raw_output=combined_output,
            execution_duration_ms=result.duration_ms,
        )

    @staticmethod
    def _extract_syntax_error(output: str) -> str:
        lines = output.splitlines()
        extracted = []
        capture = False
        for line in lines:
            if "File " in line or "SyntaxError" in line or "IndentationError" in line or "^" in line:
                capture = True
            if capture:
                extracted.append(line)
        return "\n".join(extracted[-6:]) if extracted else output[-300:]

    @staticmethod
    def _parse_pytest_output(output: str) -> Tuple[List[TestCaseResult], int, int]:
        """Parse pytest verbose output format: test_solution.py::test_name PASSED / FAILED."""
        test_cases: List[TestCaseResult] = []
        passed_count = 0
        failed_count = 0

        pattern = r"::(test_\w+)\s+(PASSED|FAILED|ERROR)"
        matches = re.findall(pattern, output)
        for test_name, status in matches:
            if status == "PASSED":
                passed_count += 1
                test_cases.append(
                    TestCaseResult(
                        name=test_name,
                        passed=True,
                        failure_category=FailureCategory.NONE,
                    )
                )
            else:
                failed_count += 1
                cat = FailureCategory.INCORRECT_OUTPUT if "FAILED" in status else FailureCategory.RUNTIME_ERROR
                test_cases.append(
                    TestCaseResult(
                        name=test_name,
                        passed=False,
                        failure_category=cat,
                    )
                )

        # If regex didn't find individual tests, check pytest summary lines (e.g., '1 failed, 2 passed in 0.05s')
        if not test_cases:
            passed_match = re.search(r"(\d+)\s+passed", output)
            failed_match = re.search(r"(\d+)\s+failed", output)
            error_match = re.search(r"(\d+)\s+error", output)

            if passed_match:
                passed_count = int(passed_match.group(1))
            if failed_match:
                failed_count += int(failed_match.group(1))
            if error_match:
                failed_count += int(error_match.group(1))

        return test_cases, passed_count, failed_count

    @staticmethod
    def _determine_failure_category(output: str) -> FailureCategory:
        """Classify failure as RUNTIME_ERROR, INCORRECT_OUTPUT, or SYNTAX_ERROR."""
        if any(err in output for err in ["AssertionError", "assert "]):
            return FailureCategory.INCORRECT_OUTPUT
        if any(
            err in output
            for err in [
                "IndexError",
                "KeyError",
                "TypeError",
                "ValueError",
                "ZeroDivisionError",
                "AttributeError",
                "NameError",
                "RecursionError",
            ]
        ):
            return FailureCategory.RUNTIME_ERROR
        if "SyntaxError" in output or "IndentationError" in output:
            return FailureCategory.SYNTAX_ERROR
        return FailureCategory.RUNTIME_ERROR

    @staticmethod
    def _build_feedback_summary(
        output: str, test_cases: List[TestCaseResult], primary_category: FailureCategory
    ) -> str:
        """Generate targeted feedback summary for the LLM repair loop."""
        lines = []
        lines.append(f"Primary Failure Classification: {primary_category.value.upper()}")

        # Extract FAILURES block from pytest
        failure_block_match = re.search(
            r"=+ FAILURES =+(.*?)(?:=+\s+short test summary info|\Z)",
            output,
            re.DOTALL,
        )
        if failure_block_match:
            lines.append("\nTest Failure Traceback:")
            lines.append(failure_block_match.group(1).strip())
        else:
            # Fallback to last 20 lines of output
            tail = "\n".join(output.splitlines()[-20:])
            lines.append("\nOutput snippet:\n" + tail)

        return "\n".join(lines)
