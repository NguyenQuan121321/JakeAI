"""Execution interface and safe local sandbox implementation."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel

from app.agent.execution.limits import ResourceLimits

logger = logging.getLogger(__name__)


class ExecutionResult(BaseModel):
    """Normalized output from sandbox execution."""

    success: bool
    output: str = ""
    error: str | None = None
    returncode: int = 0
    duration_ms: float = 0.0


class ExecutionInterface(ABC):
    """Abstract contract for sandboxed or local agent execution."""

    @abstractmethod
    async def run_command(
        self,
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecutionResult:
        """Execute command within execution boundary."""
        ...

    @abstractmethod
    async def read_file(self, rel_path: str) -> str:
        """Safely read file within sandbox workspace."""
        ...

    @abstractmethod
    async def write_file(self, rel_path: str, content: str) -> None:
        """Safely write file within sandbox workspace."""
        ...


class LocalSafeSandbox(ExecutionInterface):
    """Safe local sandbox enforcing strict path containment and command constraints.

    Prevents path traversal, resource exhaustion, and arbitrary unchecked shell execution.
    """

    ALLOWED_COMMANDS = {
        "git",
        "python",
        "pytest",
        "echo",
        "ls",
        "dir",
        "cat",
        "type",
    }

    def __init__(
        self,
        sandbox_root: str | None = None,
        limits: ResourceLimits | None = None,
    ) -> None:
        self.sandbox_root = Path(sandbox_root or os.getcwd()).resolve()
        self.limits = limits or ResourceLimits()

    def _resolve_safe_path(self, rel_path: str) -> Path:
        """Verify that resolved target path stays within sandbox boundary."""
        target = (self.sandbox_root / rel_path).resolve()
        try:
            target.relative_to(self.sandbox_root)
        except ValueError as exc:
            raise PermissionError(
                f"Path traversal rejected: '{rel_path}' escapes sandbox root '{self.sandbox_root}'"
            ) from exc
        return target

    async def read_file(self, rel_path: str) -> str:
        """Read a file within the sandbox root, respecting file size limits."""
        path = self._resolve_safe_path(rel_path)
        if not path.is_file():
            raise FileNotFoundError(f"File '{rel_path}' not found.")

        size = path.stat().st_size
        if size > self.limits.max_file_size_bytes:
            raise ValueError(
                f"File size {size} bytes exceeds limit of {self.limits.max_file_size_bytes} bytes."
            )

        with open(path, encoding="utf-8", errors="replace") as f:  # noqa: ASYNC230
            return f.read()

    async def write_file(self, rel_path: str, content: str) -> None:
        """Write a file within the sandbox root, verifying parent path containment."""
        path = self._resolve_safe_path(rel_path)
        content_bytes = content.encode("utf-8")
        if len(content_bytes) > self.limits.max_file_size_bytes:
            raise ValueError(
                f"Content size {len(content_bytes)} bytes exceeds limit of {self.limits.max_file_size_bytes} bytes."
            )

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:  # noqa: ASYNC230
            f.write(content)

    async def run_command(
        self,
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecutionResult:
        """Execute an allowlisted command with bounded timeout and output truncation."""
        start_ts = time.time()
        if not command:
            return ExecutionResult(
                success=False,
                error="Empty command provided.",
                returncode=1,
            )

        binary = Path(command[0]).name.lower().replace(".exe", "")
        if (
            binary not in self.ALLOWED_COMMANDS
            and not self.limits.allow_arbitrary_shell
        ):
            return ExecutionResult(
                success=False,
                error=f"Command '{binary}' is not permitted by safe sandbox policy.",
                returncode=126,
            )

        work_dir = self._resolve_safe_path(cwd) if cwd else self.sandbox_root

        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(work_dir),
                env=env,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.limits.timeout_seconds,
                )
            except TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    # Process already terminated; cleanup is idempotent
                    logger.debug(
                        "Process %s already exited before kill attempt.", proc.pid
                    )
                except OSError as exc:
                    logger.warning(
                        "OS error during termination of process %s: %s", proc.pid, exc
                    )
                return ExecutionResult(
                    success=False,
                    error=f"Command timed out after {self.limits.timeout_seconds} seconds.",
                    returncode=124,
                    duration_ms=(time.time() - start_ts) * 1000.0,
                )

            duration = (time.time() - start_ts) * 1000.0
            out_str = stdout_bytes.decode("utf-8", errors="replace")[
                : self.limits.max_output_bytes
            ]
            err_str = stderr_bytes.decode("utf-8", errors="replace")[
                : self.limits.max_output_bytes
            ]

            return ExecutionResult(
                success=(proc.returncode == 0),
                output=out_str,
                error=err_str if proc.returncode != 0 else None,
                returncode=proc.returncode or 0,
                duration_ms=duration,
            )
        except Exception as exc:
            return ExecutionResult(
                success=False,
                error=f"Execution failure: {exc!s}",
                returncode=1,
                duration_ms=(time.time() - start_ts) * 1000.0,
            )
