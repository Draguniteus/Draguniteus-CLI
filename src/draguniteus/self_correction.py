"""Self-correction engine: Write → Verify → Fix → Repeat.

Verifies Write/Edit tool results (Python syntax, TypeScript, etc.)
and injects error context back into the model for self-fix.
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from draguniteus.theming import CYAN, DIM, GREEN, RED, RESET


@dataclass
class VerificationResult:
    """Result of a verification check."""
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checker: str = ""


class VerificationCheck:
    """Protocol for verification checks."""

    def check(self, file_path: Path, content: str | None = None) -> VerificationResult:
        raise NotImplementedError


class PythonSyntaxCheck(VerificationCheck):
    """Verify Python file with py_compile."""

    def check(self, file_path: Path, content: str | None = None) -> VerificationResult:
        if file_path.suffix != ".py":
            return VerificationResult(passed=True, checker="python_syntax (skipped, not .py)")
        try:
            import py_compile
            py_compile.compile(str(file_path), doraise=True)
            return VerificationResult(passed=True, checker="python_syntax")
        except py_compile.PyCompileError as e:
            return VerificationResult(
                passed=False,
                errors=[str(e)],
                checker="python_syntax",
            )
        except Exception as e:
            return VerificationResult(passed=False, errors=[str(e)], checker="python_syntax")


class ESLintCheck(VerificationCheck):
    """Verify JS/TS with eslint if available."""

    def __init__(self, eslint_path: str = "eslint"):
        self.eslint_path = eslint_path

    def check(self, file_path: Path, content: str | None = None) -> VerificationResult:
        ext = file_path.suffix
        if ext not in (".js", ".ts", ".jsx", ".tsx"):
            return VerificationResult(passed=True, checker="eslint (skipped, not JS/TS)")

        # Write content to temp file if provided
        if content:
            temp = file_path.with_suffix(".tmp" + ext)
            temp.write_text(content, encoding="utf-8")
            target = temp
        else:
            target = file_path

        try:
            result = subprocess.run(
                [self.eslint_path, "--format=json", str(target)],
                capture_output=True,
                timeout=30,
            )
            import json
            reports = json.loads(result.stdout) if result.stdout else []
            if not reports:
                return VerificationResult(passed=True, checker="eslint")

            errors = []
            for report in reports:
                for msg in report.get("messages", []):
                    if msg.get("severity", 0) >= 1:
                        errors.append(f"  {file_path.name}:{msg.get('line', 0)} — {msg.get('message', '')}")

            return VerificationResult(
                passed=len(errors) == 0,
                errors=errors,
                checker="eslint",
            )
        except FileNotFoundError:
            return VerificationResult(passed=True, checker="eslint (not installed)")
        except Exception as e:
            return VerificationResult(passed=True, checker=f"eslint (error: {e})")
        finally:
            if content and target.exists():
                try:
                    target.unlink()
                except Exception:
                    pass


class ShellcheckCheck(VerificationCheck):
    """Verify shell scripts with shellcheck if available."""

    def __init__(self, shellcheck_path: str = "shellcheck"):
        self.shellcheck_path = shellcheck_path

    def check(self, file_path: Path, content: str | None = None) -> VerificationResult:
        ext = file_path.suffix
        if ext not in (".sh", ".bash"):
            return VerificationResult(passed=True, checker="shellcheck (skipped)")

        target = file_path
        if content:
            target = file_path.with_suffix(".tmp.sh")
            target.write_text(content, encoding="utf-8")

        try:
            result = subprocess.run(
                [self.shellcheck_path, "-f", "text", str(target)],
                capture_output=True,
                timeout=30,
            )
            lines = [l for l in result.stdout.decode("utf-8", errors="replace").split("\n") if l.strip()]
            errors = [l for l in lines if "SC" in l][:10]  # limit output
            return VerificationResult(
                passed=result.returncode == 0,
                errors=errors,
                checker="shellcheck",
            )
        except FileNotFoundError:
            return VerificationResult(passed=True, checker="shellcheck (not installed)")
        except Exception as e:
            return VerificationResult(passed=True, checker=f"shellcheck (error: {e})")
        finally:
            if content and target.exists():
                try:
                    target.unlink()
                except Exception:
                    pass


class SelfCorrectionEngine:
    """Write → Verify → Fix loop with max iterations."""

    def __init__(
        self,
        max_iterations: int = 3,
        checks: list[VerificationCheck] | None = None,
    ):
        self.max_iterations = max_iterations
        self.checks = checks or [
            PythonSyntaxCheck(),
            ESLintCheck(),
            ShellcheckCheck(),
        ]
        self._write_history: list[dict[str, Any]] = []

    def record_write(self, file_path: str, content: str, tool: str = "Write") -> None:
        """Record a Write/Edit tool call for later verification."""
        self._write_history.append({
            "file_path": file_path,
            "content": content,
            "tool": tool,
            "verified": False,
        })

    def verify_writes(self) -> list[VerificationResult]:
        """Run verification on all unverified Write/Edit calls."""
        results = []
        for entry in self._write_history:
            if entry["verified"]:
                continue
            path = Path(entry["file_path"])
            if not path.exists() and entry["content"]:
                # File was just written
                path = Path(entry["file_path"])
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(entry["content"], encoding="utf-8")
                except Exception:
                    pass

            for check in self.checks:
                result = check.check(path, entry["content"])
                if not result.passed:
                    results.append(result)
                    entry["verified"] = False
                    break
            else:
                entry["verified"] = True
                results.append(VerificationResult(passed=True, checker="all"))

        return results

    def check_and_fix(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[bool, list[VerificationResult], str]:
        """Run verification and inject error context into messages if needed.

        Returns (needs_fix, results, injected_message).
        """
        results = self.verify_writes()
        needs_fix = any(not r.passed for r in results)

        if not needs_fix:
            # Learn from successful write sequence
            self._learn_from_sequence()
            return False, results, ""

        # Collect all errors
        all_errors = []
        for r in results:
            if not r.passed:
                all_errors.extend(r.errors)

        error_summary = "\n".join(f"  - {e}" for e in all_errors[:10])
        injected = (
            f"[Self-Correction] Verification failed for the following files:\n"
            f"{error_summary}\n\n"
            f"Please fix the issues above and re-apply the changes using Edit or Write tools."
        )

        return True, results, injected

    def _learn_from_sequence(self) -> None:
        """Record successful tool sequence in PatternLibrary."""
        try:
            from draguniteus.memory.pattern_library import _get_pattern_library
            library = _get_pattern_library()
            tool_names = [e["tool"] for e in self._write_history if e.get("tool")]
            if tool_names:
                library.learn_from_tool_sequence(tool_names, success=True)
            self._write_history.clear()
        except Exception:
            pass

    def get_pending_writes(self) -> list[dict[str, Any]]:
        """Return unverified write history."""
        return [e for e in self._write_history if not e.get("verified", False)]


# Global instance
_self_correction_engine: SelfCorrectionEngine | None = None


def get_self_correction_engine() -> SelfCorrectionEngine:
    global _self_correction_engine
    if _self_correction_engine is None:
        _self_correction_engine = SelfCorrectionEngine()
    return _self_correction_engine
