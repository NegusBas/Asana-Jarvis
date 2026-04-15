"""Git operations for the Scivora (or any configured) repository."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class GitAgent:
    """Run read-only / safe git commands in a fixed repo directory."""

    repo_path: Optional[str] = None

    def __post_init__(self) -> None:
        self.repo_path = self.repo_path or os.getenv(
            "SCIVORA_REPO_PATH",
            os.path.expanduser("~/Projects/scivora"),
        )

    def _run(self, *args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def status(self) -> str:
        p = self._run("status", "--branch", "--porcelain")
        return self._format("git status", p)

    def pull(self) -> str:
        p = self._run("pull", "--ff-only")
        return self._format("git pull --ff-only", p)

    def log(self, n: int = 20) -> str:
        p = self._run(
            "log",
            f"-{n}",
            "--date=short",
            "--pretty=format:%h %ad %s (%an)",
        )
        return self._format(f"git log -{n}", p)

    def sync_and_summarize(self, log_lines: int = 15) -> str:
        """Pull fast-forward only, then show status + recent commits."""
        parts = [self.pull(), self.status(), self.log(log_lines)]
        return "\n\n".join(parts)

    @staticmethod
    def _format(title: str, proc: subprocess.CompletedProcess[str]) -> str:
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        body = out or "(no stdout)"
        if err:
            body += f"\nstderr:\n{err}"
        return f"=== {title} (exit {proc.returncode}) ===\n{body}"
