"""
Draguniteus Benchmark Suite
Run identical tasks through Draguniteus and Claude Code, score results objectively.
"""
import subprocess
import time
import json
import shutil
import os
import sys
from pathlib import Path
from datetime import datetime

BENCHMARK_DIR = Path("/tmp/draguniteus_benchmark")
RESULTS_FILE = BENCHMARK_DIR / "results.json"

BENCHMARK_TASKS = [
    {
        "id": "fastapi_auth",
        "name": "FastAPI Auth Service",
        "description": "Build a FastAPI auth service with JWT, user model, and login endpoint",
        "difficulty": "hard",
        "timeout": 300,
        "expected_files": ["main.py", "auth.py", "models.py", "schemas.py"],
        "verification": "python -c 'import main; print(\"imports ok\")'",
    },
    {
        "id": "multi_file_pkg",
        "name": "Multi-File Python Package",
        "description": "Create a Python package with __init__.py, 3 modules, and relative imports",
        "difficulty": "medium",
        "timeout": 180,
        "expected_files": ["mylib/__init__.py", "mylib/core.py", "mylib/utils.py", "mylib/main.py"],
        "verification": "python -c 'import mylib; print(\"imports ok\")'",
    },
    {
        "id": "react_component",
        "name": "React Component Library",
        "description": "Create 5 React components with props, state, and TypeScript types",
        "difficulty": "hard",
        "timeout": 300,
        "expected_files": ["Button.tsx", "Card.tsx", "Modal.tsx", "Input.tsx", "Select.tsx"],
        "verification": None,  # No Node verification needed, just file existence
    },
    {
        "id": "bug_fix_py",
        "name": "Python Bug Fix",
        "description": "Fix the syntax and logic errors in broken Python code",
        "difficulty": "medium",
        "timeout": 120,
        "expected_files": ["fixed.py"],
        "verification": "python fixed.py",
    },
    {
        "id": "git_script",
        "name": "Git Automation Script",
        "description": "Write a shell script that automates git branch creation, commit, and PR creation",
        "difficulty": "medium",
        "timeout": 120,
        "expected_files": ["git workflow.sh"],
        "verification": "bash git_workflow.sh --help",
    },
]


def run_task_draguniteus(task: dict, workspace: Path) -> dict:
    """Run a task through Draguniteus CLI."""
    start = time.time()
    workspace.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "draguniteus",
        "--non-interactive",
        "--task", task["description"],
        "--output-dir", str(workspace),
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=task["timeout"],
        cwd=str(workspace),
    )

    elapsed = time.time() - start

    files_created = []
    if workspace.exists():
        for f in workspace.rglob("*"):
            if f.is_file():
                rel = f.relative_to(workspace)
                files_created.append(str(rel))

    return {
        "agent": "Draguniteus",
        "elapsed": elapsed,
        "exit_code": result.returncode,
        "stdout": result.stdout[:2000],
        "stderr": result.stderr[:1000],
        "files_created": files_created,
        "expected_found": [ef for ef in task["expected_files"] if any(ef in f for f in files_created)],
    }


def score_result(result: dict, task: dict) -> dict:
    """Score a benchmark result objectively."""
    files_found = len(result.get("expected_found", []))
    files_expected = len(task["expected_files"])
    file_score = (files_found / files_expected) * 50 if files_expected > 0 else 0

    runtime_score = 20 if result["elapsed"] < task["timeout"] * 0.8 else 10
    exit_score = 15 if result["exit_code"] == 0 else 0
    completeness_score = 15 if files_found == files_expected else 0

    total = file_score + runtime_score + exit_score + completeness_score

    return {
        "file_score": round(file_score, 1),
        "runtime_score": runtime_score,
        "exit_score": exit_score,
        "completeness_score": completeness_score,
        "total": round(total, 1),
    }


def run_benchmark():
    """Run the full benchmark suite."""
    results = {
        "timestamp": datetime.now().isoformat(),
        "tasks": [],
        "summary": {},
    }

    for task in BENCHMARK_TASKS:
        print(f"\n{'='*60}")
        print(f"Running: {task['name']} ({task['difficulty']})")
        print(f"{'='*60}")

        workspace = BENCHMARK_DIR / task["id"]
        shutil.rmtree(workspace, ignore_errors=True)

        # Run Draguniteus
        try:
            dr_result = run_task_draguniteus(task, workspace)
            scores = score_result(dr_result, task)
            dr_result["scores"] = scores
            print(f"  Draguniteus: {scores['total']}/100 ({dr_result['elapsed']:.1f}s)")
            print(f"  Files: {len(dr_result['files_created'])} created, "
                  f"{scores['file_score']}/50 on expected files")
        except subprocess.TimeoutExpired:
            dr_result = {"agent": "Draguniteus", "error": "timeout", "elapsed": task["timeout"]}
            dr_result["scores"] = {"total": 0, "file_score": 0, "runtime_score": 0, "exit_score": 0, "completeness_score": 0}
            print(f"  Draguniteus: TIMEOUT ({task['timeout']}s)")
        except Exception as e:
            dr_result = {"agent": "Draguniteus", "error": str(e)}
            dr_result["scores"] = {"total": 0}
            print(f"  Draguniteus: ERROR - {e}")

        task_result = {
            "task_id": task["id"],
            "task_name": task["name"],
            "difficulty": task["difficulty"],
            "draguniteus": dr_result,
        }
        results["tasks"].append(task_result)

    # Summary
    totals = [t["draguniteus"]["scores"]["total"] for t in results["tasks"]]
    results["summary"] = {
        "draguniteus_avg": round(sum(totals) / len(totals), 1) if totals else 0,
        "total_tasks": len(BENCHMARK_TASKS),
    }

    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*60}")
    print(f"BENCHMARK COMPLETE")
    print(f"{'='*60}")
    print(f"Draguniteus Average Score: {results['summary']['draguniteus_avg']}/100")
    print(f"Results saved to: {RESULTS_FILE}")

    return results


if __name__ == "__main__":
    run_benchmark()
