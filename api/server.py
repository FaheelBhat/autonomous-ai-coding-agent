"""FastAPI REST application exposing coding agent endpoints."""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from database.db import DatabaseManager
from schemas.models import ExecutionReport, TaskCreateRequest, TaskResponse, TaskStatus
from agent.orchestrator import CodingAgent

logger = logging.getLogger("api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

app = FastAPI(
    title="Autonomous AI Coding Agent API",
    description="REST API for submitting coding tasks, generating solutions, isolated testing, and iterative self-repair.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = DatabaseManager()
agent = CodingAgent(db_manager=db)
thread_pool = ThreadPoolExecutor(max_workers=4)


@app.get("/health", status_code=status.HTTP_200_OK, tags=["System"])
def health_check():
    """Service health check and environment status."""
    docker_ready = agent.sandbox.is_docker_available()
    return {
        "status": "healthy",
        "service": "autonomous-ai-coding-agent",
        "docker_sandbox_available": docker_ready,
        "llm_provider": agent.llm.__class__.__name__,
    }


@app.post(
    "/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Tasks"],
)
def submit_task(request: TaskCreateRequest):
    """
    Submit a programming problem for autonomous synthesis, execution, testing, and repair.
    Validates inputs and triggers background execution.
    """
    import uuid
    task_id = str(uuid.uuid4())

    db.create_task(
        task_id=task_id,
        prompt=request.prompt,
        requirements=request.requirements,
        language=request.language,
        max_repair_attempts=request.max_repair_attempts,
    )

    def run_worker():
        try:
            agent.run_task(request=request, task_id=task_id)
        except Exception as e:
            logger.error("Error executing task %s in background worker: %s", task_id, e)

    thread_pool.submit(run_worker)

    task_res = db.get_task(task_id)
    if not task_res:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register task in database.",
        )
    return task_res


@app.get("/tasks/{task_id}", response_model=TaskResponse, tags=["Tasks"])
def get_task_status(task_id: str):
    """Retrieve current processing status and results for a given task ID."""
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with ID '{task_id}' was not found.",
        )
    return task


@app.get("/tasks/{task_id}/report", response_model=ExecutionReport, tags=["Tasks"])
def get_task_report(task_id: str):
    """Retrieve structured execution report for a completed task."""
    report = db.get_report(task_id)
    if not report:
        task = db.get_task(task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task with ID '{task_id}' does not exist.",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task '{task_id}' is currently {task.status.value}. Execution report is not yet available.",
        )
    return report
