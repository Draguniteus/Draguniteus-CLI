"""Orchestration tools: parallel multi-agent execution."""
from __future__ import annotations

from typing import Any


ORCHESTRATION_TOOLS = [
    {
        "name": "Orchestrate",
        "description": "Break a complex task into subtasks and execute them in parallel using multiple specialized agents. Use when a task has independent parts that can run simultaneously. Returns combined results from all agents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Overall task description"
                },
                "subtasks": {
                    "type": "array",
                    "description": "List of subtask specifications",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Agent name (e.g. 'explorer', 'coder', 'reviewer')"},
                            "task": {"type": "string", "description": "What this agent should do"},
                            "model": {
                                "type": "string",
                                "enum": ["MiniMax-M2.7", "MiniMax-M2.5", "MiniMax-M2.1", "MiniMax-M2"],
                                "description": "Model to use (M2.7 for reasoning, M2.5 for code, M2.1 for fast, M2 for agentic)"
                            },
                            "tools": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Specific tools to grant (None = all tools)"
                            },
                            "timeout_seconds": {
                                "type": "number",
                                "default": 120.0,
                                "description": "Max seconds before subagent times out"
                            }
                        },
                        "required": ["name", "task"]
                    }
                },
                "timeout_per_agent": {
                    "type": "number",
                    "description": "Default timeout in seconds for all subagents (default 120s)",
                    "default": 120.0
                }
            },
            "required": ["task", "subtasks"]
        }
    },
    {
        "name": "MultiAgentReview",
        "description": "Run a coordinated multi-agent code review. Spawns explorer, security reviewer, and performance reviewer agents in parallel, then aggregates findings.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "File or directory to review"
                },
                "focus": {
                    "type": "string",
                    "description": "Review focus: 'security', 'performance', 'correctness', or 'all' (default)"
                }
            },
            "required": ["target"]
        }
    }
]


def tool_orchestrate(task: str, subtasks: list[dict[str, Any]], **kwargs) -> str:
    """Execute a task using multiple specialized agents in parallel."""
    try:
        from draguniteus.orchestrator import MultiAgentOrchestrator, AgentSpec
        from draguniteus.config import Config

        config = Config()
        orchestrator = MultiAgentOrchestrator(config)

        # Build AgentSpec list
        specs = []
        for st in subtasks:
            spec = AgentSpec(
                name=st["name"],
                task=st["task"],
                model=st.get("model", "MiniMax-M2.7"),
                tools=st.get("tools"),
                max_turns=st.get("max_turns", 10),
                timeout_seconds=st.get("timeout_seconds", 120.0),
            )
            specs.append(spec)

        progress_callback = kwargs.get("progress_callback")

        results = orchestrator.orchestrate(
            task, specs, [],
            "",
            timeout_per_agent=kwargs.get("timeout_per_agent", 120.0),
            progress_callback=progress_callback,
        )
        return orchestrator.aggregate(results, task)
    except Exception as e:
        return f"Orchestration error: {e}"


def tool_multiagent_review(target: str, focus: str = "all", **kwargs) -> str:
    """Run a coordinated multi-agent review on code."""
    try:
        from draguniteus.orchestrator import MultiAgentOrchestrator, AgentSpec
        from draguniteus.config import Config

        config = Config()
        orchestrator = MultiAgentOrchestrator(config)

        subtasks = [
            AgentSpec(
                name="explorer",
                task=f"Analyze {target} and understand its structure, purpose, and key components. List the main functions/classes and their roles.",
                model="MiniMax-M2.7"
            ),
            AgentSpec(
                name="security",
                task=f"Review {target} for security issues: SQL injection, XSS, command injection, auth bypass, secrets in code, insecure dependencies.",
                model="MiniMax-M2.5"
            ),
            AgentSpec(
                name="performance",
                task=f"Review {target} for performance problems: N+1 queries, missing indexes, memory leaks, expensive operations in loops, lack of caching.",
                model="MiniMax-M2.5"
            ),
        ]

        if focus == "security":
            subtasks = [subtasks[1]]
        elif focus == "performance":
            subtasks = [subtasks[2]]
        elif focus == "correctness":
            subtasks = [subtasks[0], subtasks[2]]

        results = orchestrator.orchestrate(f"Review {target}", subtasks, [], "")
        return orchestrator.aggregate(results, f"Review of {target}")
    except Exception as e:
        return f"Multi-agent review error: {e}"
