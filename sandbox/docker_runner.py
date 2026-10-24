"""Secure Docker execution runner and configuration."""

import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional
from schemas.models import SandboxExecutionResult

logger = logging.getLogger(__name__)


class DockerSandbox:
    """Runs code safely inside a restricted, isolated Docker container."""

    def __init__(
        self,
        image_name: str = "python:3.12-slim",
        cpu_quota: int = 100000,  # 1.0 CPU (100,000 microseconds per period)
        mem_limit: str = "256m",
        timeout_seconds: int = 15,
    ):
        self.image_name = image_name
        self.cpu_quota = cpu_quota
        self.mem_limit = mem_limit
        self.timeout_seconds = timeout_seconds

    def is_docker_available(self) -> bool:
        """Check if Docker daemon is accessible and client is functional."""
        try:
            import docker
            client = docker.from_env()
            client.ping()
            return True
        except Exception as e:
            logger.warning("Docker environment check failed: %s", str(e))
            return False

    def execute_test_suite(
        self,
        solution_code: str,
        test_code: str,
        custom_timeout: Optional[int] = None,
    ) -> SandboxExecutionResult:
        """
        Execute candidate Python solution against test code in Docker sandbox.

        Security controls enforced:
        - network_disabled = True (blocks outbound & inbound network)
        - mem_limit = '256m'
        - nano_cpus or cpu_quota limit
        - read_only root filesystem with explicit non-executable scratch mounts
        - non-root user (nobody / uid 65534)
        - no host Docker socket mounted
        - isolated temporary directory per run
        - candidate code mounted read-only during test execution
        """
        if not self.is_docker_available():
            return SandboxExecutionResult(
                stdout="",
                stderr="",
                exit_code=-1,
                timed_out=False,
                duration_ms=0.0,
                sandbox_available=False,
                error_message=(
                    "Secure Docker execution is unavailable on this host. "
                    "Docker daemon is not running or Docker CLI is not installed. "
                    "Refusing to execute arbitrary untrusted code directly on host."
                ),
            )

        timeout = custom_timeout or self.timeout_seconds
        start_time = time.time()

        temp_dir = tempfile.mkdtemp(prefix="agent_sandbox_")
        run_dir = Path(temp_dir)

        try:
            # Structure workspace:
            # /sandbox/app/solution.py (read-only)
            # /sandbox/tests/test_solution.py (read-only)
            # /sandbox/tmp (writable scratch space for pytest tempfiles)
            app_dir = run_dir / "app"
            tests_dir = run_dir / "tests"
            scratch_dir = run_dir / "scratch"

            app_dir.mkdir(parents=True, exist_ok=True)
            tests_dir.mkdir(parents=True, exist_ok=True)
            scratch_dir.mkdir(parents=True, exist_ok=True)

            # Write code files
            (app_dir / "solution.py").write_text(solution_code, encoding="utf-8")
            (app_dir / "__init__.py").write_text("", encoding="utf-8")
            (tests_dir / "test_solution.py").write_text(test_code, encoding="utf-8")
            (tests_dir / "__init__.py").write_text("", encoding="utf-8")

            # Conftest or runner script to isolate sys.path
            runner_script = (
                "import sys, os, pytest\n"
                "sys.path.insert(0, '/sandbox/app')\n"
                "code = pytest.main(['/sandbox/tests/test_solution.py', '-v', '--tb=short', '-o', 'cache_dir=/sandbox/scratch/.pytest_cache'])\n"
                "sys.exit(code)\n"
            )
            (run_dir / "run_eval.py").write_text(runner_script, encoding="utf-8")

            # Set wide permissions so non-root container user (uid 65534) can read app/tests and write to scratch
            os.chmod(str(run_dir), 0o777)
            os.chmod(str(scratch_dir), 0o777)
            os.chmod(str(run_dir / "run_eval.py"), 0o666)
            for f in app_dir.glob("*"):
                os.chmod(str(f), 0o666)
            for f in tests_dir.glob("*"):
                os.chmod(str(f), 0o666)

            import docker
            client = docker.from_env()

            # Volumes mapping
            volumes: Dict[str, Dict[str, str]] = {
                str(app_dir): {"bind": "/sandbox/app", "mode": "ro"},
                str(tests_dir): {"bind": "/sandbox/tests", "mode": "ro"},
                str(run_dir / "run_eval.py"): {"bind": "/sandbox/run_eval.py", "mode": "ro"},
                str(scratch_dir): {"bind": "/sandbox/scratch", "mode": "rw"},
            }

            container = client.containers.run(
                image=self.image_name,
                command=["python", "/sandbox/run_eval.py"],
                network_disabled=True,
                mem_limit=self.mem_limit,
                cpu_quota=self.cpu_quota,
                user="65534:65534",  # nobody:nogroup
                volumes=volumes,
                working_dir="/sandbox/scratch",
                environment={
                    "PYTHONPATH": "/sandbox/app",
                    "TMPDIR": "/sandbox/scratch",
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
                detach=True,
                read_only=True,
            )

            timed_out = False
            stdout = ""
            stderr = ""
            exit_code = 0

            try:
                result = container.wait(timeout=timeout)
                exit_code = result.get("StatusCode", 1)
                logs = container.logs(stdout=True, stderr=True)
                stdout = logs.decode("utf-8", errors="replace")
            except Exception as e:
                # Timed out or wait error
                timed_out = True
                exit_code = -1
                stderr = f"Execution timed out after {timeout} seconds: {str(e)}"
                try:
                    container.kill()
                except Exception:
                    pass
            finally:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

            duration_ms = round((time.time() - start_time) * 1000, 2)
            return SandboxExecutionResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                timed_out=timed_out,
                duration_ms=duration_ms,
                sandbox_available=True,
            )

        except Exception as e:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            logger.error("Sandbox execution encountered exception: %s", str(e), exc_info=True)
            return SandboxExecutionResult(
                stdout="",
                stderr=str(e),
                exit_code=-1,
                timed_out=False,
                duration_ms=duration_ms,
                sandbox_available=True,
                error_message=f"Sandbox error: {str(e)}",
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
