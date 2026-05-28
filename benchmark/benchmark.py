"""
Draguniteus Benchmark Suite
==========================
Runs a series of challenging coding tasks through Draguniteus.
Each task is scored on: correctness, completeness, and performance.

The SAME tasks are attempted by Claude Code (this session) for comparison.
"""
import sys
import os
import time
import shutil
import subprocess
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from draguniteus.client import DraguniteusClient
from draguniteus.config import Config


@dataclass
class TaskResult:
    task_id: str
    task_name: str
    difficulty: str
    draguniteus_score: float = 0.0
    draguniteus_time: float = 0.0
    draguniteus_files: list = field(default_factory=list)
    draguniteus_error: Optional[str] = None
    claude_code_score: float = 0.0
    claude_code_time: float = 0.0
    claude_code_files: list = field(default_factory=list)
    claude_code_error: Optional[str] = None
    winner: Optional[str] = None
    notes: str = ""


BENCHMARK_TASKS = [
    {
        "id": "fastapi_auth",
        "name": "FastAPI Authentication Service",
        "prompt": """Create a complete FastAPI authentication service at /tmp/benchmark_workspace/fastapi_auth/

Requirements:
1. main.py - FastAPI app with /auth/login and /auth/register endpoints
2. models.py - User model with id, username, email, password_hash fields
3. schemas.py - Pydantic schemas for login/registration requests
4. auth.py - JWT token creation and validation functions
5. requirements.txt - fastapi, uvicorn, pyjwt, passlib, python-multipart

Use Python 3.12+. Write all files with proper imports. After writing, run: pip install -q -r requirements.txt && python -c "from main import app; print('OK')".""",
        "expected_files": ["main.py", "models.py", "schemas.py", "auth.py", "requirements.txt"],
        "verify_cmd": "python -c \"from main import app; from auth import create_token; print('OK')\"",
        "timeout": 300,
    },
    {
        "id": "python_package",
        "name": "Python Multi-File Package",
        "prompt": """Create a Python package at /tmp/benchmark_workspace/mypackage/

Structure:
- mypackage/__init__.py - exports Animal, Dog, Cat classes
- mypackage/animals.py - Base Animal class with name and speak() method
- mypackage/dogs.py - Dog class that inherits Animal, says "woof"
- mypackage/cats.py - Cat class that inherits Animal, says "meow"
- mypackage/main.py - Creates Dog and Cat instances and prints their sounds

Use relative imports within the package. After writing all files, run: cd /tmp/benchmark_workspace && python -c "from mypackage import Dog, Cat; d = Dog('Buddy'); print(d.speak())".""",
        "expected_files": ["mypackage/__init__.py", "mypackage/animals.py", "mypackage/dogs.py", "mypackage/cats.py", "mypackage/main.py"],
        "verify_cmd": "python -c \"from mypackage import Dog, Cat; d = Dog('Buddy'); c = Cat('Whiskers'); print(d.speak(), c.speak())\"",
        "timeout": 180,
    },
    {
        "id": "react_components",
        "name": "React TypeScript Component Library",
        "prompt": """Create a React component library at /tmp/benchmark_workspace/ui-components/

Create these TypeScript React components with full props and TypeScript types:
1. Button.tsx - variant (primary|secondary|ghost), size (sm|md|lg), children, onClick
2. Card.tsx - title, description, children, footer slot
3. Modal.tsx - isOpen, onClose, title, children props
4. Input.tsx - label, type, placeholder, value, onChange, error message
5. Select.tsx - label, options array, value, onChange

Use React 18 with proper TypeScript generics where appropriate. Export each component.""",
        "expected_files": ["Button.tsx", "Card.tsx", "Modal.tsx", "Input.tsx", "Select.tsx"],
        "verify_cmd": None,  # Just check files exist and have valid TSX syntax
        "timeout": 300,
    },
    {
        "id": "git_workflow_script",
        "name": "Git Workflow Automation Script",
        "prompt": """Write a bash script at /tmp/benchmark_workspace/gitflow.sh that automates a git branching workflow:

Features:
1. ./gitflow.sh start <branch-name> - creates and switches to new branch
2. ./gitflow.sh commit <message> - stages all changes and commits with message
3. ./gitflow.sh pr - creates a GitHub PR (uses gh CLI if available)
4. ./gitflow.sh status - shows current branch and changed files
5. ./gitflow.sh finish - merges branch to main and deletes it

Include error handling, argument validation, and colored output. Make it executable. Test with ./gitflow.sh --help.""",
        "expected_files": ["gitflow.sh"],
        "verify_cmd": "bash /tmp/benchmark_workspace/gitflow.sh --help",
        "timeout": 120,
    },
    {
        "id": "debug_python",
        "name": "Python Debug & Fix",
        "prompt": """Fix all bugs in /tmp/benchmark_workspace/broken.py. The file contains:
- A function that parses CSV data and returns aggregated statistics
- Several bugs: syntax errors, logic errors, and edge case failures

Read the file, identify ALL bugs, fix them, and verify by running: python /tmp/benchmark_workspace/broken.py
The expected output is: "total=150, average=30.0, count=5".""",
        "expected_files": ["broken.py"],
        "verify_cmd": "python /tmp/benchmark_workspace/broken.py",
        "timeout": 180,
        "setup": "echo 'name,value\\nitem1,10\\nitem2,20\\nitem3,30\\nitem4,40\\nitem5,50' > /tmp/benchmark_workspace/broken.py && echo 'import csv\\nfrom io import StringIO\\n\\ndef parse_csv(csv_text):\\n    reader = csv.DictReader(StringIO(csv_text))\\n    total = sum(int(row[\"value\"]) for row in reader)\\n    count = 5\\n    return total, total/count, count\\n\\ncsv_data = \"\"\"\\nname,value\\nitem1,10\\nitem2,20\\nitem3,30\\nitem4,40\\nitem5,50\\n\"\"\"\\n\\nt, avg, c = parse_csv(csv_data)\\nprint(f\"total={t}, average={avg}, count={c}\")\\n' > /tmp/benchmark_workspace/broken.py"
    },
    {
        "id": "self_correct",
        "name": "Self-Correction Loop",
        "prompt": """Write a Python file at /tmp/benchmark_workspace/stats.py that:
1. Defines calculate_stats(numbers) that returns (sum, average)
2. Has a typo bug on purpose: uses 'number' instead of 'numbers' on one line
3. Then runs the function with [1,2,3,4,5] and prints the result

After writing, run: python /tmp/benchmark_workspace/stats.py
If there's an error, fix it and run again. Report the final output.""",
        "expected_files": ["stats.py"],
        "verify_cmd": "python /tmp/benchmark_workspace/stats.py",
        "timeout": 120,
    },
    {
        "id": "bash_script",
        "name": "System Admin Bash Script",
        "prompt": """Write a system administration script at /tmp/benchmark_workspace/sysadmin.sh:

Features:
1. Disk usage report: shows usage for /, /home, /tmp (df -h)
2. Top 5 processes by memory (ps aux --sort=-%mem | head -6)
3. Services in failed state (systemctl list-units --state=failed)
4. Largest files in /var/log (du -sh /var/log/* | sort -rh | head -5)
5. Docker container status (docker ps -a --format "table {{.Names}}\\t{{.Status}}")

Use colored output, error handling, and a --report flag to run all checks at once.""",
        "expected_files": ["sysadmin.sh"],
        "verify_cmd": "bash /tmp/benchmark_workspace/sysadmin.sh --report 2>&1 | head -20",
        "timeout": 120,
    },
    {
        "id": "async_fastapi",
        "name": "Async FastAPI with Database",
        "prompt": """Create an async FastAPI application at /tmp/benchmark_workspace/async_api/

Files:
1. main.py - FastAPI app with async /items endpoint (GET, POST)
2. database.py - Async SQLite with aiosqlite, init_db function
3. models.py - SQLAlchemy models for Item (id, name, description, created_at)
4. schemas.py - Pydantic schemas for ItemCreate, ItemResponse
5. requirements.txt - fastapi, uvicorn, aiosqlite, sqlalchemy

After writing, verify: pip install -q -r requirements.txt && python -c "from main import app; print('async OK')".""",
        "expected_files": ["main.py", "database.py", "models.py", "schemas.py", "requirements.txt"],
        "verify_cmd": "pip install -q aiosqlite sqlalchemy && python -c \"from main import app; print('async OK')\"",
        "timeout": 300,
    },
]


def run_task_draguniteus(task: dict, workspace: Path) -> dict:
    """Run a task through Draguniteus streaming client."""
    if task.get("setup"):
        subprocess.run(task["setup"], shell=True, capture_output=True)

    workspace.mkdir(parents=True, exist_ok=True)

    client = DraguniteusClient(Config())
    messages = [{"role": "user", "content": task["prompt"]}]

    start = time.time()
    text = ""
    thinking = ""

    try:
        stream = client.stream(
            messages=messages,
            model="MiniMax-M2.7",
            max_tokens=8192,
            system="You are Draguniteus, an expert coding agent. Write complete, working code. After writing files, verify by running the verification command.",
        )

        for event in stream:
            if hasattr(event, 'type'):
                if event.type == 'content_block_delta':
                    delta = getattr(event, 'delta', None)
                    if delta:
                        if hasattr(delta, 'text') and delta.text:
                            text += delta.text
                        elif hasattr(delta, 'thinking') and delta.thinking:
                            thinking += delta.thinking
                elif event.type == 'message_stop':
                    break

        elapsed = time.time() - start

        files_created = [str(f.relative_to(workspace))
                        for f in workspace.rglob("*") if f.is_file() and not f.name.startswith('.')]

        return {
            "elapsed": elapsed,
            "text": text[:3000],
            "thinking": thinking[:1000],
            "files_created": files_created,
            "error": None,
        }

    except Exception as e:
        elapsed = time.time() - start
        return {
            "elapsed": elapsed,
            "text": "",
            "thinking": "",
            "files_created": [],
            "error": str(e),
        }


def verify_task(task: dict, workspace: Path) -> dict:
    """Verify a task by running its verification command."""
    verify_cmd = task.get("verify_cmd")
    if not verify_cmd:
        expected = task["expected_files"]
        found = [f for f in expected if any(f in str(p) for p in workspace.rglob("*"))]
        return {"passed": len(found) == len(expected), "output": f"{len(found)}/{len(expected)} files"}

    try:
        result = subprocess.run(
            verify_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(workspace.parent),
        )
        output = (result.stdout + result.stderr).strip()
        passed = result.returncode == 0
        return {"passed": passed, "output": output[:500], "returncode": result.returncode}
    except subprocess.TimeoutExpired:
        return {"passed": False, "output": "timeout", "returncode": -1}
    except Exception as e:
        return {"passed": False, "output": str(e), "returncode": -1}


def score_result(result: dict, task: dict, verification: dict) -> float:
    """Score a result out of 100."""
    score = 0.0

    # Files created (40 points)
    expected = task["expected_files"]
    found = [f for f in expected if any(f in str(p) for p in Path("/tmp/benchmark_workspace", task["id"]).rglob("*") if p.is_file())]
    file_ratio = len(found) / len(expected) if expected else 0
    score += file_ratio * 40

    # Verification passed (40 points)
    if verification.get("passed"):
        score += 40
    elif verification.get("output") and verification["output"] != "timeout":
        # Partial credit for partial output
        score += 20

    # Completion time (20 points) - only if verification passed
    if verification.get("passed"):
        elapsed = result.get("elapsed", 999)
        timeout = task.get("timeout", 300)
        if elapsed < timeout * 0.5:
            score += 20
        elif elapsed < timeout * 0.8:
            score += 15
        else:
            score += 10

    return round(score, 1)


def run_full_benchmark():
    """Run all benchmark tasks."""
    print("=" * 70)
    print("DRAGUNITEUS BENCHMARK SUITE")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    all_results = []

    for task in BENCHMARK_TASKS:
        print(f"\n{'─' * 70}")
        print(f"Task: {task['name']} [{task['id']}] ({task['difficulty']})")
        print(f"{'─' * 70}")

        workspace = Path("/tmp/benchmark_workspace") / task["id"]

        # Clean workspace
        shutil.rmtree(workspace, ignore_errors=True)

        # Run Draguniteus
        print(f"  Running Draguniteus (timeout={task['timeout']}s)...")
        dr_result = run_task_draguniteus(task, workspace)

        # Verify
        verification = verify_task(task, workspace)
        score = score_result(dr_result, task, verification)

        files_created = [str(f.relative_to(workspace))
                        for f in workspace.rglob("*") if f.is_file() and not f.name.startswith('.')]

        print(f"  Score: {score}/100")
        print(f"  Time: {dr_result['elapsed']:.1f}s")
        print(f"  Files: {len(files_created)}/{len(task['expected_files'])}")
        print(f"  Verified: {'✅' if verification['passed'] else '❌'} {verification.get('output', '')[:80]}")

        if dr_result.get("error"):
            print(f"  Error: {dr_result['error'][:200]}")

        result_entry = {
            "task_id": task["id"],
            "task_name": task["name"],
            "difficulty": task["difficulty"],
            "draguniteus_score": score,
            "draguniteus_time": round(dr_result["elapsed"], 1),
            "draguniteus_files": files_created,
            "draguniteus_verified": verification["passed"],
            "draguniteus_error": dr_result.get("error"),
        }
        all_results.append(result_entry)

    # Summary
    total_score = sum(r["draguniteus_score"] for r in all_results)
    avg_score = total_score / len(all_results) if all_results else 0
    verified_count = sum(1 for r in all_results if r["draguniteus_verified"])

    print(f"\n{'=' * 70}")
    print("BENCHMARK RESULTS SUMMARY")
    print(f"{'=' * 70}")
    print(f"Total Tasks: {len(all_results)}")
    print(f"Tasks Verified: {verified_count}/{len(all_results)}")
    print(f"Average Score: {avg_score:.1f}/100")
    print()
    print(f"{'Task':<30} {'Score':>8} {'Time':>8} {'Verified':>10}")
    print("-" * 60)
    for r in sorted(all_results, key=lambda x: -x["draguniteus_score"]):
        ver = "✅" if r["draguniteus_verified"] else "❌"
        print(f"{r['task_name']:<30} {r['draguniteus_score']:>7.1f} {r['draguniteus_time']:>7.1f}s {ver:>10}")

    # Save results
    output_file = Path("/tmp/benchmark_results.json")
    with open(output_file, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": all_results,
            "summary": {
                "average_score": round(avg_score, 1),
                "verified": verified_count,
                "total": len(all_results),
            }
        }, f, indent=2)

    print(f"\nResults saved to: {output_file}")
    return all_results


if __name__ == "__main__":
    import json
    from datetime import datetime
    run_full_benchmark()
