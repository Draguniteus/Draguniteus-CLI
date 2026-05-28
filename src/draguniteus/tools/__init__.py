"""Tools package."""
from draguniteus.tools.filesystem import FILESYSTEM_TOOLS, tool_read, tool_write, tool_edit, tool_multi_edit, tool_glob, tool_grep
from draguniteus.tools.shell import SHELL_TOOLS, tool_bash
from draguniteus.tools.git import GIT_TOOLS, tool_git_status, tool_git_diff, tool_git_commit, tool_git_push, tool_git_pr_create, tool_git_auto_commit
from draguniteus.tools.memory import MEMORY_TOOLS, tool_write_daily_note, tool_read_daily_note, tool_write_project_memory, tool_read_project_memory
from draguniteus.tools.web import WEB_TOOLS, tool_webfetch, tool_websearch
from draguniteus.tools.agent import AGENT_TOOLS, tool_agent
from draguniteus.tools.code_intelligence import (
    CODE_INDEX_TOOLS,
    tool_index_code,
    tool_find_symbol,
    tool_go_to_definition,
    tool_find_references,
)
from draguniteus.tools.minimax import (
    MINIMAX_TOOLS,
    tool_text_to_audio, tool_list_voices, tool_voice_clone,
    tool_text_to_image, tool_generate_video, tool_music_generation,
    tool_query_video_generation, tool_image_to_video,
)
from draguniteus.tools.orchestrate import ORCHESTRATION_TOOLS, tool_orchestrate, tool_multiagent_review
from draguniteus.tools.navigation import NAVIGATION_TOOLS, tool_semantic_search, tool_explain_code, tool_index_semantic
from draguniteus.tools.review import REVIEW_TOOLS, tool_start_code_review, tool_stop_code_review, tool_get_review_findings
from draguniteus.tools.diff_tools import DIFF_TOOLS, tool_diff, tool_diff_staged
from draguniteus.tools.inspect import INSPECT_TOOLS, tool_inspect_environment
from draguniteus.voice import VOICE_TOOLS
from draguniteus.voice.pair import tool_voice_start, tool_voice_stop, tool_voice_speak, tool_voice_listen

ALL_TOOLS = (
    FILESYSTEM_TOOLS + SHELL_TOOLS + GIT_TOOLS + MEMORY_TOOLS +
    WEB_TOOLS + AGENT_TOOLS + CODE_INDEX_TOOLS + MINIMAX_TOOLS +
    ORCHESTRATION_TOOLS + NAVIGATION_TOOLS + REVIEW_TOOLS + VOICE_TOOLS + DIFF_TOOLS + INSPECT_TOOLS
)

TOOL_MAP = {
    # Filesystem
    "Read": tool_read,
    "Write": tool_write,
    "Edit": tool_edit,
    "MultiEdit": tool_multi_edit,
    "Glob": tool_glob,
    "Grep": tool_grep,
    # Shell
    "Bash": tool_bash,
    # Git
    "GitAutoCommit": tool_git_auto_commit,
    "GitStatus": tool_git_status,
    "GitDiff": tool_git_diff,
    "GitCommit": tool_git_commit,
    "GitPush": tool_git_push,
    "GitPRCreate": tool_git_pr_create,
    # Memory
    "WriteDailyNote": tool_write_daily_note,
    "ReadDailyNote": tool_read_daily_note,
    "WriteProjectMemory": tool_write_project_memory,
    "ReadProjectMemory": tool_read_project_memory,
    # Web
    "WebFetch": tool_webfetch,
    "WebSearch": tool_websearch,
    # Agent
    "Agent": tool_agent,
    # Code intelligence
    "IndexCode": tool_index_code,
    "FindSymbol": tool_find_symbol,
    "GoToDefinition": tool_go_to_definition,
    "FindReferences": tool_find_references,
    # MiniMax media
    "text_to_audio": tool_text_to_audio,
    "list_voices": tool_list_voices,
    "voice_clone": tool_voice_clone,
    "text_to_image": tool_text_to_image,
    "generate_video": tool_generate_video,
    "music_generation": tool_music_generation,
    "query_video_generation": tool_query_video_generation,
    "image_to_video": tool_image_to_video,
    # Orchestration
    "Orchestrate": tool_orchestrate,
    "MultiAgentReview": tool_multiagent_review,
    # Navigation
    "SemanticSearch": tool_semantic_search,
    "ExplainCode": tool_explain_code,
    "IndexSemantic": tool_index_semantic,
    # Review
    "StartCodeReview": tool_start_code_review,
    "StopCodeReview": tool_stop_code_review,
    "GetReviewFindings": tool_get_review_findings,
    # Voice
    "voice_start": tool_voice_start,
    "voice_stop": tool_voice_stop,
    "voice_speak": tool_voice_speak,
    "voice_listen": tool_voice_listen,
    # Diff
    "tool_diff": tool_diff,
    "tool_diff_staged": tool_diff_staged,
    # Inspect
    "InspectEnvironment": tool_inspect_environment,
}
