"""Integration and unit tests for FastAPI REST endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from api.server import app, agent, db
from schemas.models import SandboxExecutionResult, TaskStatus


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "docker_sandbox_available" in data


def test_submit_task_validation_error(client):
    # Short prompt should fail Pydantic validation (422)
    response = client.post("/tasks", json={"prompt": "abc"})
    assert response.status_code == 422


def test_submit_and_get_task(client):
    # Mock sandbox to execute deterministically
    mock_sandbox = MagicMock()
    mock_sandbox.execute_test_suite.return_value = SandboxExecutionResult(
        stdout="test_solution.py::test_ok PASSED\n1 passed in 0.01s",
        stderr="",
        exit_code=0,
        sandbox_available=True,
    )
    agent.sandbox = mock_sandbox

    # Submit task
    response = client.post(
        "/tasks",
        json={
            "prompt": "Write a function returning True.",
            "max_repair_attempts": 1,
        },
    )
    assert response.status_code == 202
    data = response.json()
    task_id = data["task_id"]
    assert task_id is not None

    # Retrieve task status
    get_res = client.get(f"/tasks/{task_id}")
    assert get_res.status_code == 200
    assert get_res.json()["task_id"] == task_id


def test_get_nonexistent_task(client):
    res = client.get("/tasks/non-existent-id")
    assert res.status_code == 404
