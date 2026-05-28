"""
Draguniteus Benchmark Runner
Executes benchmark tasks and scores results.
"""
import sys
import os
import time
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

# Setup path
BENCHMARK_DIR = Path("/tmp/benchmark_workspace")
BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from draguniteus.client import DraguniteusClient
from draguniteus.config import Config


def run_draguniteus_task(prompt: str, workspace: Path, timeout: int = 300) -> dict:
    """Run a task through Draguniteus streaming client."""
    client = DraguniteusClient(Config())
    messages = [{"role": "user", "content": prompt}]

    start_time = time.time()
    full_text = ""
    thinking_text = ""

    try:
        stream = client.stream(
            messages=messages,
            model="MiniMax-M2.7",
            max_tokens=8192,
            system="""You are Draguniteus, an expert coding agent. You have access to these tools:
- Write: write content to a file
- Bash: run shell commands
- Read: read file contents

IMPORTANT: You must actually call tools to write files. Just calling them is not enough - you need to use the Write tool to create files on disk. After writing files, run the verification command to check your work.
Always use the Bash tool to run verification commands after writing files.""",
        )

        for event in stream:
            if hasattr(event, 'type'):
                if event.type == 'content_block_delta':
                    delta = getattr(event, 'delta', None)
                    if delta:
                        if hasattr(delta, 'text') and delta.text:
                            full_text += delta.text
                        elif hasattr(delta, 'thinking') and delta.thinking:
                            thinking_text += delta.thinking
                elif event.type == 'message_stop':
                    break

        elapsed = time.time() - start_time

    except Exception as e:
        elapsed = time.time() - start_time
        return {
            "elapsed": elapsed,
            "text": full_text[:3000],
            "thinking": thinking_text[:1000],
            "files_created": [],
            "error": str(e),
            "success": False,
        }

    # Get files actually created
    files_created = []
    if workspace.exists():
        for f in workspace.rglob("*"):
            if f.is_file() and not f.name.startswith('.'):
                files_created.append(str(f.relative_to(workspace)))

    return {
        "elapsed": elapsed,
        "text": full_text[:3000],
        "thinking": thinking_text[:1000],
        "files_created": files_created,
        "error": None,
        "success": True,
    }


def verify_task(workspace: Path, expected_files: list, verify_cmd: str) -> dict:
    """Verify a task by running its verification command."""
    if not workspace.exists():
        return {"passed": False, "output": "workspace does not exist", "score": 0}

    # Check expected files
    existing_files = []
    for f in workspace.rglob("*"):
        if f.is_file() and not f.name.startswith('.'):
            existing_files.append(str(f.relative_to(workspace)))

    found_count = sum(1 for ef in expected_files if any(ef in str(p) for p in existing_files))
    file_score = (found_count / len(expected_files)) * 50 if expected_files else 0

    if not verify_cmd:
        return {
            "passed": found_count == len(expected_files),
            "files_found": found_count,
            "files_expected": len(expected_files),
            "output": f"{found_count}/{len(expected_files)} files",
            "score": file_score,
        }

    # Run verification command
    try:
        result = subprocess.run(
            verify_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(workspace.parent) if workspace.parent.exists() else "/tmp",
        )
        output = (result.stdout + result.stderr).strip()[:500]
        passed = result.returncode == 0

        # Full score = file score + verification
        verify_score = 50 if passed else 0
        total_score = file_score + verify_score

        return {
            "passed": passed,
            "returncode": result.returncode,
            "output": output,
            "score": round(total_score, 1),
            "file_score": round(file_score, 1),
            "files_found": found_count,
            "files_expected": len(expected_files),
        }

    except subprocess.TimeoutExpired:
        return {"passed": False, "output": "timeout", "score": file_score, "file_score": round(file_score, 1)}
    except Exception as e:
        return {"passed": False, "output": str(e), "score": file_score, "file_score": round(file_score, 1)}


def run_benchmark_task(task_def: dict) -> dict:
    """Run a single benchmark task."""
    task_id = task_def["id"]
    workspace = BENCHMARK_DIR / task_id

    # Clean workspace
    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True, exist_ok=True)

    # Run Draguniteus
    dr_result = run_draguniteus_task(task_def["prompt"], workspace, task_def.get("timeout", 300))

    # Verify
    verification = verify_task(workspace, task_def.get("expected_files", []), task_def.get("verify_cmd", ""))

    return {
        "task_id": task_id,
        "task_name": task_def["name"],
        "difficulty": task_def["difficulty"],
        "draguniteus": {
            "elapsed": round(dr_result["elapsed"], 1),
            "files_created": dr_result.get("files_created", []),
            "text_preview": dr_result["text"][:500],
            "error": dr_result.get("error"),
        },
        "verification": verification,
        "score": verification.get("score", 0),
    }


def run_all_benchmarks():
    """Run all benchmark tasks."""
    from benchmark.tasks import TASKS

    print("=" * 70)
    print("DRAGUNITEUS BENCHMARK SUITE — MiniMax M2.7")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Tasks: {len(TASKS)}")
    print()

    results = []

    for i, task in enumerate(TASKS):
        print(f"\n[{i+1}/{len(TASKS)}] {task.name} ({task.difficulty})")
        print("-" * 50)

        result = run_benchmark_task({
            "id": task.id,
            "name": task.name,
            "difficulty": task.difficulty,
            "prompt": task.prompt,
            "expected_files": task.expected_files,
            "verify_cmd": task.verify_cmd,
            "timeout": 300,
        })

        results.append(result)

        score = result["score"]
        ver = result["verification"]
        dr = result["draguniteus"]

        print(f"  Score: {score}/100")
        print(f"  Time: {dr['elapsed']:.1f}s")
        print(f"  Files: {ver.get('files_found', 0)}/{ver.get('files_expected', 0)}")
        print(f"  Verified: {'✅' if ver['passed'] else '❌'} {ver.get('output', '')[:60]}")

        if dr.get("error"):
            print(f"  Error: {dr['error'][:100]}")

    # Summary
    total_score = sum(r["score"] for r in results)
    avg_score = total_score / len(results) if results else 0
    verified = sum(1 for r in results if r["verification"]["passed"])

    print(f"\n{'=' * 70}")
    print("FINAL RESULTS")
    print(f"{'=' * 70}")
    print(f"Total: {avg_score:.1f}/100 average ({verified}/{len(results)} tasks verified)")
    print()

    # Sort by difficulty
    for diff in ["extreme", "hard", "medium"]:
        diff_results = [r for r in results if r["difficulty"] == diff]
        if diff_results:
            diff_avg = sum(r["score"] for r in diff_results) / len(diff_results)
            print(f"  {diff.upper()}: {diff_avg:.1f}/100 ({len(diff_results)} tasks)")

    print()
    print(f"{'Task':<30} {'Score':>8} {'Time':>8} {'Status':>10}")
    print("-" * 60)
    for r in sorted(results, key=lambda x: -x["score"]):
        status = "✅" if r["verification"]["passed"] else "❌"
        print(f"{r['task_name']:<30} {r['score']:>7.1f} {r['draguniteus']['elapsed']:>7.1f}s {status:>10}")

    # Save results
    output = {
        "timestamp": datetime.now().isoformat(),
        "model": "MiniMax-M2.7",
        "summary": {
            "average_score": round(avg_score, 1),
            "verified": verified,
            "total": len(results),
            "total_time": sum(r["draguniteus"]["elapsed"] for r in results),
        },
        "results": results,
    }

    output_file = Path("/tmp/benchmark_results.json")
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nResults: {output_file}")
    return output


if __name__ == "__main__":
    run_all_benchmarks()
