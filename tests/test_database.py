"""Unit tests for SQLite database operations and serialization."""

import tempfile
from datetime import datetime
from database.db import DatabaseManager
from schemas.models import ExecutionReport, TaskCreateRequest, TaskStatus


def test_database_task_lifecycle():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db = DatabaseManager(db_path=tmp.name)

        task_id = "test-task-123"
        db.create_task(
            task_id=task_id,
            prompt="Reverse a linked list",
            requirements="O(1) auxiliary space",
            language="python",
            max_repair_attempts=3,
        )

        task = db.get_task(task_id)
        assert task is not None
        assert task.task_id == task_id
        assert task.status == TaskStatus.PENDING

        # Update status
        db.update_task_status(task_id, TaskStatus.GENERATING)
        task_updated = db.get_task(task_id)
        assert task_updated.status == TaskStatus.GENERATING

        # Save report
        report = ExecutionReport(
            task_id=task_id,
            original_task="Reverse a linked list",
            final_code="def reverse(head): return head",
            brief_explanation="Reverses in place.",
            generated_tests="def test_rev(): assert True",
            repair_attempts_used=0,
            max_repair_attempts=3,
            final_status=TaskStatus.COMPLETED,
            all_tests_passed=True,
            test_summary={"passed": 1, "failed": 0},
            created_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )

        db.save_execution_report(task_id, report)

        saved_report = db.get_report(task_id)
        assert saved_report is not None
        assert saved_report.task_id == task_id
        assert saved_report.all_tests_passed is True

        task_final = db.get_task(task_id)
        assert task_final.status == TaskStatus.COMPLETED
        assert task_final.report is not None
