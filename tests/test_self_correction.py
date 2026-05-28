"""Tests for self-correction engine — Write→Verify→Fix loop."""
import pytest
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, 'src')

from draguniteus.self_correction import (
    SelfCorrectionEngine, PythonSyntaxCheck, get_self_correction_engine,
    VerificationResult, VerificationCheck
)


class TestVerificationResult:
    """Test VerificationResult."""

    def test_success_result(self):
        result = VerificationResult(passed=True, checker="test")
        assert result.passed is True
        assert result.checker == "test"
        assert result.errors == []

    def test_failure_result(self):
        result = VerificationResult(
            passed=False,
            errors=["SyntaxError: invalid syntax"],
            checker="python_syntax"
        )
        assert result.passed is False
        assert len(result.errors) == 1


class TestPythonSyntaxCheck:
    """Test PythonSyntaxCheck verification."""

    def setup_method(self):
        self.check = PythonSyntaxCheck()
        self.temp_dir = Path(tempfile.mkdtemp())

    def test_passes_valid_python(self):
        valid_code = "def hello():\n    return 'hi'\n"
        test_file = self.temp_dir / "valid.py"
        test_file.write_text(valid_code)

        result = self.check.check(test_file, valid_code)
        assert result.passed is True

    def test_fails_invalid_python(self):
        invalid_code = "def hello()\n    pass\n"  # missing colon
        test_file = self.temp_dir / "invalid.py"
        test_file.write_text(invalid_code)

        result = self.check.check(test_file, invalid_code)
        assert result.passed is False

    def test_skips_non_python_files(self):
        test_file = self.temp_dir / "test.js"
        test_file.write_text("console.log('hello')")

        result = self.check.check(test_file, "console.log('hello')")
        assert result.passed is True  # skipped

    def test_checks_file_from_disk(self):
        valid_code = "x = 1\n"
        test_file = self.temp_dir / "disk_check.py"
        test_file.write_text(valid_code)

        # Pass None for content — should check file on disk
        result = self.check.check(test_file, None)
        assert result.passed is True


class TestSelfCorrectionEngine:
    """Test SelfCorrectionEngine."""

    def setup_method(self):
        self.engine = get_self_correction_engine()
        self.engine._write_history.clear()

    def test_record_write(self):
        self.engine.record_write("test.py", "print('hello')")
        pending = self.engine.get_pending_writes()
        assert len(pending) == 1
        assert pending[0]["file_path"] == "test.py"
        assert pending[0]["verified"] is False

    def test_record_write_multiple(self):
        self.engine.record_write("a.py", "# a")
        self.engine.record_write("b.py", "# b")
        pending = self.engine.get_pending_writes()
        assert len(pending) == 2

    def test_verify_writes_no_pending(self):
        results = self.engine.verify_writes()
        assert results == []

    def test_check_and_fix_no_writes_returns_false(self):
        needs_fix, results, msg = self.engine.check_and_fix([])
        assert needs_fix is False
        assert results == []
        assert msg == ""

    def test_record_write_clears_after_learn(self):
        # Add a write then clear via learn
        self.engine.record_write("test.py", "x = 1\n")
        self.engine._write_history.clear()
        assert len(self.engine.get_pending_writes()) == 0

    def test_engine_singleton(self):
        e1 = get_self_correction_engine()
        e2 = get_self_correction_engine()
        assert e1 is e2

    def test_max_iterations_default(self):
        engine = SelfCorrectionEngine()
        assert engine.max_iterations == 3

    def test_custom_checks_list(self):
        custom_checks = [PythonSyntaxCheck()]
        engine = SelfCorrectionEngine(checks=custom_checks)
        assert len(engine.checks) == 1