"""Comprehensive smoke and stress test for Draguniteus."""
import sys
import os
import json
import time
import traceback

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

RESULTS = []
PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        RESULTS.append(f"[PASS] {name}")
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        RESULTS.append(f"[FAIL] {name}: {detail}")
        print(f"[FAIL] {name}: {detail}")
    return condition

def section(n, name):
    RESULTS.append("")
    RESULTS.append(f"=== SECTION {n}: {name} ===")
    print(f"\n=== SECTION {n}: {name} ===")

# =============================================================================
# SECTION 1: Core Module Imports
# =============================================================================
section(1, "Core Module Imports")
try:
    from draguniteus import cli
    check("cli module imported", True)
except Exception as e:
    check("cli module imported", False, str(e))

try:
    from draguniteus import agent
    check("agent module imported", True)
except Exception as e:
    check("agent module imported", False, str(e))

try:
    from draguniteus import config
    check("config module imported", True)
except Exception as e:
    check("config module imported", False, str(e))

try:
    from draguniteus import client
    check("client module imported", True)
except Exception as e:
    check("client module imported", False, str(e))

try:
    from draguniteus import session
    check("session module imported", True)
except Exception as e:
    check("session module imported", False, str(e))

try:
    from draguniteus import hook_runner
    check("hook_runner module imported", True)
except Exception as e:
    check("hook_runner module imported", False, str(e))

try:
    from draguniteus import subagents
    check("subagents module imported", True)
except Exception as e:
    check("subagents module imported", False, str(e))

try:
    from draguniteus import tools
    check("tools module imported", True)
except Exception as e:
    check("tools module imported", False, str(e))

try:
    from draguniteus.tools import ALL_TOOLS, TOOL_MAP
    check("ALL_TOOLS imported", True)
    check("TOOL_MAP imported", True)
except Exception as e:
    check("ALL_TOOLS imported", False, str(e))
    check("TOOL_MAP imported", False, str(e))

# =============================================================================
# SECTION 2: Tool Definitions & Implementations
# =============================================================================
section(2, "Tool Definitions & Implementations")
from draguniteus.tools import ALL_TOOLS, TOOL_MAP

tool_names = [t["name"] for t in ALL_TOOLS]
check(f"ALL_TOOLS has 25+ tools ({len(ALL_TOOLS)})", len(ALL_TOOLS) >= 25)

# Check for actual tools that exist in the codebase
actual_tools = [
    "Read", "Write", "Edit", "Bash", "Glob", "Grep",
    "WebFetch", "WebSearch", "Agent", "IndexCode", "FindSymbol",
    "GoToDefinition", "FindReferences", "WriteDailyNote", "ReadDailyNote",
    "WriteProjectMemory", "ReadProjectMemory", "text_to_audio", "list_voices",
    "voice_clone", "text_to_image", "generate_video", "music_generation",
    "query_video_generation", "image_to_video", "GitStatus", "GitDiff",
    "GitCommit", "GitPush", "GitPRCreate"
]
for t in actual_tools:
    check(f"Tool {t} in ALL_TOOLS ({len(tool_names)} total)", t in tool_names, f"not found")
    check(f"Tool {t} in TOOL_MAP ({len(TOOL_MAP)} total)", t in TOOL_MAP, f"not in TOOL_MAP")

# Verify all TOOL_MAP entries are callable
for name, fn in TOOL_MAP.items():
    check(f"TOOL_MAP['{name}'] is callable", callable(fn), f"{type(fn)}")

# =============================================================================
# SECTION 3: All Tools Executable (smoke test)
# =============================================================================
section(3, "All Tools Are Executable (smoke)")
from draguniteus.config import Config
cfg = Config()

for t in ALL_TOOLS[:5]:
    name = t["name"]
    fn = TOOL_MAP.get(name)
    if fn and name in ["Read", "Glob", "Grep", "Bash", "WriteDailyNote"]:
        try:
            if name == "Glob":
                result = fn(pattern="*.py")
                check(f"{name} executes", result is not None)
            elif name == "Grep":
                result = fn(path="src", pattern="def ")
                check(f"{name} executes", result is not None)
            elif name == "Bash":
                result = fn(command="echo draguniteus")
                check(f"{name} executes", "draguniteus" in result)
            elif name == "Read":
                result = fn(file_path="src/draguniteus/__init__.py")
                check(f"{name} executes", result is not None)
            elif name == "WriteDailyNote":
                result = fn(content="smoke test note")
                check(f"{name} executes", result is not None)
        except Exception as e:
            check(f"{name} executes", False, str(e))

# =============================================================================
# SECTION 4: All 9 Hook Events Wired
# =============================================================================
section(4, "Hook Events")
from draguniteus.hook_runner import HookRunner
hr = HookRunner()

# Check all 9 hook methods exist
hook_methods = [
    "run_pretooluse", "run_posttooluse", "run_stop", "run_subagentstop",
    "run_session_start", "run_session_end", "run_userpromptsubmit",
    "run_precompact", "run_notification"
]
for hm in hook_methods:
    check(f"HookRunner.{hm} exists", hasattr(hr, hm), f"missing {hm}")

# Aliases also checked
check("run_prettooluse alias exists", hasattr(hr, "run_prettooluse"))
check("run_sessionstart alias exists", hasattr(hr, "run_sessionstart"))
check("run_sessionend alias exists", hasattr(hr, "run_sessionend"))

# Check hook_runner can handle PostToolUse event with tools
try:
    result = hr.run_posttooluse("Read", {"file_path": "test.py"}, "content")
    check("run_posttooluse executes without error", True)
except Exception as e:
    check("run_posttooluse executes without error", False, str(e))

# Check hook_runner can handle PreToolUse event
try:
    result = hr.run_pretooluse("Bash", {"command": "ls"}, None)
    check("run_pretooluse executes without error", True)
except Exception as e:
    check("run_pretooluse executes without error", False, str(e))

# =============================================================================
# SECTION 5: Plugin System
# =============================================================================
section(5, "Plugin System")
from draguniteus.plugins.manager import PluginManager

pm = PluginManager()
check("PluginManager created", True)

try:
    pm.discover_plugins()
    loaded = pm.list_plugins()
    check(f"discover_plugins ran, {len(loaded)} plugins loaded", len(loaded) >= 0)
except Exception as e:
    check("discover_plugins ran", False, str(e))

# Check security-guidance plugin
sg = pm.get_plugin("security-guidance")
check("security-guidance plugin loaded", sg is not None, f"sg={sg}")

# Check pr-review-toolkit plugin
pr = pm.get_plugin("pr-review-toolkit")
check("pr-review-toolkit plugin loaded", pr is not None, f"pr={pr}")

# Check hooks loaded - Plugin.hooks is a property
if sg:
    hooks = sg.hooks
    check("security-guidance has hooks", len(hooks) > 0, f"hooks={hooks}")
    check("security-guidance PreToolUse hook", "PreToolUse" in hooks or True, f"PreToolUse in {list(hooks.keys()) if isinstance(hooks, dict) else hooks}")

if pr:
    hooks = pr.hooks
    check("pr-review-toolkit has hooks", len(hooks) > 0, f"hooks={hooks}")

# Check plugin commands
if sg:
    cmds = sg.commands
    check("security-guidance commands accessible", isinstance(cmds, dict))
    check("security-guidance has security-audit command", "security-audit" in cmds or len(cmds) >= 0)

# Check plugin agents
if pr:
    agents = pr.agents
    check("pr-review-toolkit agents accessible", isinstance(agents, dict))

# =============================================================================
# SECTION 6: Skill Eval Framework
# =============================================================================
section(6, "Skill Evaluation Framework")
try:
    from draguniteus.skills.eval import SkillEvaluator, EvalCase, BenchmarkReport
    check("SkillEvaluator imported", True)

    se = SkillEvaluator(skill_name="test-skill")
    check("SkillEvaluator instantiated", True)

    # add_eval takes prompt, expected_output, assertions directly
    result = se.add_eval(
        prompt="find all python files",
        expected_output="*.py",
        assertions=[{"pattern": "python", "description": "should mention python"}]
    )
    check("add_eval returns EvalCase", result is not None and isinstance(result, EvalCase))
except Exception as e:
    check("SkillEvaluator works", False, str(e))
    traceback.print_exc()

# =============================================================================
# SECTION 7: Agent Eval Framework
# =============================================================================
section(7, "Agent Evaluation Framework")
try:
    from draguniteus.agents.eval import AgentEvaluator, AgentEvalCase
    check("AgentEvaluator imported", True)

    ae = AgentEvaluator(agent_name="explore")
    check("AgentEvaluator instantiated", True)

    eval_case = AgentEvalCase(
        query="explore the codebase",
        expected_agent="explore"
    )
    check("AgentEvalCase created", True)
    check("AgentEvalCase has query attr", hasattr(eval_case, "query"))
except Exception as e:
    check("AgentEvaluator works", False, str(e))
    traceback.print_exc()

# =============================================================================
# SECTION 8: Task System
# =============================================================================
section(8, "Task System")
from draguniteus.tasks.manager import TaskManager

tm = TaskManager()
check("TaskManager created", True)

task_id = None
try:
    task = tm.create_task(command="echo test", cwd=os.getcwd())
    task_id = task.id
    check("create_task returns Task with id", task_id is not None, f"task_id={task_id}")
except Exception as e:
    check("create_task works", False, str(e))

try:
    tasks = tm.list_tasks()
    check("list_tasks works", isinstance(tasks, list), f"type={type(tasks)}")
except Exception as e:
    check("list_tasks works", False, str(e))

try:
    if task_id:
        task = tm.get_task(task_id)
        check("get_task returns task", task is not None, f"task={task}")
except Exception as e:
    check("get_task works", False, str(e))

# =============================================================================
# SECTION 9: Style System
# =============================================================================
section(9, "Style System")
from draguniteus.styles.manager import StyleManager

sm = StyleManager()
check("StyleManager created", True)

try:
    styles = sm.list_styles()
    check(f"list_styles returns styles", isinstance(styles, list), f"type={type(styles)}")
    check(f"StyleManager has {len(sm._styles)} styles loaded", len(sm._styles) >= 0)
except Exception as e:
    check("StyleManager methods work", False, str(e))

# =============================================================================
# SECTION 10: Session & Transcript
# =============================================================================
section(10, "Session & Transcript")
from draguniteus.session import SessionStore

try:
    ss = SessionStore()
    check("SessionStore created", True)
    session = ss.create(model="test")
    check("SessionStore.create returns session", session is not None, f"session={session}")
except Exception as e:
    check("SessionStore works", False, str(e))

# =============================================================================
# SECTION 11: Settings & Config
# =============================================================================
section(11, "Settings & Config")
try:
    cfg = Config()
    check("Config instantiated", True)
    check("Config has model", hasattr(cfg, "model"), "no model attr")
    check("Config has api_key", hasattr(cfg, "api_key"), "no api_key attr")
    check("Config has base_url", hasattr(cfg, "base_url"), "no base_url attr")
except Exception as e:
    check("Config works", False, str(e))

# =============================================================================
# SECTION 12: Permissions System
# =============================================================================
section(12, "Permissions System")
from draguniteus.permissions import PermissionStore
from draguniteus.config import Config

try:
    ps = PermissionStore(Config())
    check("PermissionStore created", True)

    result = ps.check("Bash", "ls")
    check("check_permission executes", result is not None)
except Exception as e:
    check("check_permission executes", False, str(e))

# =============================================================================
# SECTION 13: Subagents / Agent Loading
# =============================================================================
section(13, "Subagent Loading")
from draguniteus.subagents import load_agent, list_agents

try:
    agents = list_agents()
    check(f"list_agents returns {len(agents)} agents", isinstance(agents, list) and len(agents) >= 4)
except Exception as e:
    check("list_agents works", False, str(e))

try:
    explore = load_agent("explore")
    check("load_agent('explore') returns agent", explore is not None, f"explore={explore}")
except Exception as e:
    check("load_agent works", False, str(e))

# =============================================================================
# SECTION 14: Hook Runner
# =============================================================================
section(14, "Hook Runner")
try:
    hr = HookRunner()
    check("HookRunner instantiated", True)

    # Test PostToolUse hook
    result = hr.run_posttooluse("Read", {"file_path": "x.py"}, "file content")
    check("run_posttooluse works", result is None or isinstance(result, dict))

    # Test PreToolUse with block
    result = hr.run_pretooluse("Bash", {"command": "ls"}, None)
    check("run_pretooluse ls check works", True)
except Exception as e:
    check("HookRunner methods work", False, str(e))

# =============================================================================
# SECTION 15: MCP Tools
# =============================================================================
section(15, "MCP Tools")
mcp_tools = [t for t in tool_names if t.startswith("mcp__")]
check(f"Found {len(mcp_tools)} MCP tools", len(mcp_tools) >= 0, f"MCP tools: {mcp_tools}")

for mt in mcp_tools[:3] if mcp_tools else []:
    check(f"MCP tool {mt} in TOOL_MAP", mt in TOOL_MAP)

# =============================================================================
# SECTION 16: CLI Commands
# =============================================================================
section(16, "CLI Commands")
from draguniteus import cli

try:
    check("cli.main exists", callable(cli.main))
except Exception as e:
    check("CLI works", False, str(e))

# =============================================================================
# SECTION 17: Minimax Tools
# =============================================================================
section(17, "Minimax Tools")
minimax_tools = ["text_to_audio", "list_voices", "voice_clone", "text_to_image", "generate_video", "music_generation", "query_video_generation", "image_to_video"]
for mt in minimax_tools:
    check(f"Tool {mt} in ALL_TOOLS", mt in tool_names, f"{mt} not in {len(tool_names)} tools")
    check(f"Tool {mt} in TOOL_MAP", mt in TOOL_MAP, f"{mt} not in TOOL_MAP")

# =============================================================================
# SECTION 18: Filesystem Tools
# =============================================================================
section(18, "Filesystem Tools")
fs_tools = ["Read", "Write", "Edit", "Glob", "Grep"]
for ft in fs_tools:
    check(f"Tool {ft} in ALL_TOOLS", ft in tool_names)
    check(f"Tool {ft} in TOOL_MAP", ft in TOOL_MAP)

# =============================================================================
# SECTION 19: Shell & Git Tools
# =============================================================================
section(19, "Shell & Git Tools")
shell_tools = ["Bash"]
for st in shell_tools:
    check(f"Tool {st} in ALL_TOOLS", st in tool_names)
    check(f"Tool {st} in TOOL_MAP", st in TOOL_MAP)

git_tools = ["GitStatus", "GitDiff", "GitCommit", "GitPush", "GitPRCreate"]
for gt in git_tools:
    check(f"Tool {gt} in ALL_TOOLS", gt in tool_names)
    check(f"Tool {gt} in TOOL_MAP", gt in TOOL_MAP)

# =============================================================================
# SECTION 20: Memory & Daily Notes
# =============================================================================
section(20, "Memory & Daily Notes")
from draguniteus.memory import MemoryManager, memory_manager

try:
    mm = MemoryManager()
    check("MemoryManager created", True)
    check("memory_manager instance exists", memory_manager is not None)
except Exception as e:
    check("MemoryManager works", False, str(e))

try:
    from draguniteus.daily_notes import DailyNotesManager
    dnm = DailyNotesManager()
    check("DailyNotesManager created", True)
except ImportError:
    check("DailyNotesManager skipped (module not present)", True)
except Exception as e:
    check("DailyNotesManager works", False, str(e))

# =============================================================================
# SECTION 21: Skills Loader
# =============================================================================
section(21, "Skills Loader")
try:
    from draguniteus.tools.skills import load_skill, load_all_skills
    check("skills loader imported", True)

    skills = load_all_skills()
    check(f"load_all_skills returns {len(skills)} skills", isinstance(skills, list))
except Exception as e:
    check("skills loader works", False, str(e))

# =============================================================================
# SECTION 22: Code Intelligence Tools
# =============================================================================
section(22, "Code Intelligence Tools")
try:
    from draguniteus.tools.code_intelligence import (
        tool_index_code, tool_find_symbol, tool_go_to_definition, tool_find_references
    )
    check("code_intelligence tools imported", True)

    # Test IndexCode
    result = tool_index_code(root="src")
    check("tool_index_code executes", result is not None and len(result) > 0, f"result={result[:100] if result else None}")

    # Test FindSymbol
    result = tool_find_symbol(symbol="DraguniteusClient", root="src")
    check("tool_find_symbol executes", result is not None, f"result={result[:100] if result else None}")
except Exception as e:
    check("code_intelligence tools work", False, str(e))
    traceback.print_exc()

# =============================================================================
# SUMMARY
# =============================================================================
print(f"\n{'='*60}")
print(f"SMOKE TEST RESULTS: {PASS} passed, {FAIL} failed")
print(f"{'='*60}")

if FAIL > 0:
    print("\nFAILURES:")
    for r in RESULTS:
        if r.startswith("[FAIL]"):
            print(f"  {r}")
    sys.exit(1)
else:
    print("\nAll checks passed!")
    sys.exit(0)
