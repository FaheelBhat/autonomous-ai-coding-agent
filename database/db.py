"""SQLite persistence layer for tasks and execution reports."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from schemas.models import ExecutionReport, TaskResponse, TaskStatus


class DatabaseManager:
    """Manages SQLite storage for autonomous coding agent tasks and reports."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = Path(__file__).resolve().parent.parent
            self.db_path = str(base_dir / "agent_tasks.db")
        else:
            self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create necessary tables if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    requirements TEXT,
                    language TEXT NOT NULL,
                    max_repair_attempts INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS execution_reports (
                    task_id TEXT PRIMARY KEY,
                    report_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks (task_id) ON DELETE CASCADE
                )
            """)
            conn.commit()

    def create_task(
        self,
        task_id: str,
        prompt: str,
        requirements: Optional[str],
        language: str,
        max_repair_attempts: int,
    ) -> None:
        """Insert a newly initiated task."""
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO tasks (
                    task_id, status, prompt, requirements, language,
                    max_repair_attempts, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    TaskStatus.PENDING.value,
                    prompt,
                    requirements,
                    language,
                    max_repair_attempts,
                    now,
                    now,
                ),
            )
            conn.commit()

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        error: Optional[str] = None,
    ) -> None:
        """Update current processing status of a task."""
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE tasks
                SET status = ?, error = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (status.value, error, now, task_id),
            )
            conn.commit()

    def save_execution_report(self, task_id: str, report: ExecutionReport) -> None:
        """Save full structured execution report and mark task completion."""
        # Clean sensitive keys defensively before serialization
        report_dict = report.model_dump()
        report_json = json.dumps(report_dict, default=str)
        now = datetime.utcnow().isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO execution_reports (task_id, report_json, created_at)
                VALUES (?, ?, ?)
                """,
                (task_id, report_json, now),
            )
            cursor.execute(
                """
                UPDATE tasks
                SET status = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (report.final_status.value, now, task_id),
            )
            conn.commit()

    def get_task(self, task_id: str) -> Optional[TaskResponse]:
        """Fetch a task along with its report if available."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT task_id, status, created_at, updated_at, error FROM tasks WHERE task_id = ?",
                (task_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            cursor.execute(
                "SELECT report_json FROM execution_reports WHERE task_id = ?",
                (task_id,),
            )
            report_row = cursor.fetchone()
            report: Optional[ExecutionReport] = None
            if report_row:
                try:
                    data = json.loads(report_row["report_json"])
                    report = ExecutionReport.model_validate(data)
                except Exception:
                    report = None

            return TaskResponse(
                task_id=row["task_id"],
                status=TaskStatus(row["status"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                report=report,
                error=row["error"],
            )

    def get_report(self, task_id: str) -> Optional[ExecutionReport]:
        """Directly retrieve execution report for a task."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT report_json FROM execution_reports WHERE task_id = ?",
                (task_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            data = json.loads(row["report_json"])
            return ExecutionReport.model_validate(data)

    def list_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List recent tasks."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT task_id, status, prompt, language, created_at, updated_at
                FROM tasks
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
