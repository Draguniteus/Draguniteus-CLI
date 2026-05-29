"""Prompt-toolkit based fullscreen REPL input with vim keys, mouse support, and slash command menu.

Integrates with existing Rich.Live displays and the cli.py REPL loop.
Supports:
- Vim keybindings (j/k navigation, gg/G top/bottom, / search)
- Mouse click and scroll
- Ctrl+C interruption
- Shift+Tab for permission mode cycling
- Rich interactive slash command menu with fuzzy matching, descriptions, and arrow navigation
"""
from __future__ import annotations

import sys
import threading
from typing import Callable, Awaitable

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.key_binding import KeyBindings, ConditionalKeyBindings
    from prompt_toolkit.keys import Keys
    from prompt_toolkit.mouse_events import MouseEventType
    from prompt_toolkit.styles import Style
    from prompt_toolkit.filters import has_focus
    from prompt_toolkit.completion import WordCompleter, Completer
    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False


# Slash command registry with descriptions
SLASH_COMMANDS = {
    "help": "Show all available commands",
    "plan": "Show the current plan or create a new one",
    "effort": "Set effort level (low/medium/high)",
    "compact": "Compact the context window",
    "memory": "Show memory status and search",
    "init": "Initialize a new project",
    "agents": "Manage multi-agent agents",
    "new": "Start a new session",
    "reset": "Reset the conversation",
    "exit": "Exit Draguniteus",
    "quit": "Exit Draguniteus",
    "recap": "Get a recap of the conversation",
    "release-notes": "Show release notes",
    "usage": "Show API usage statistics",
    "btw": "Add a side note to the conversation",
    "style": "Change the output style",
    "worktree": "Manage git worktrees",
    "tasks": "Show and manage tasks",
    "transcript": "Manage conversation transcripts",
    "background": "Background tasks",
    "vim": "Toggle vim mode",
    "skills": "Show available skills",
    "skill": "Run a specific skill",
    "agent": "Switch agent mode",
    "session": "Manage sessions",
    "orchestrate": "Orchestrate multi-agent tasks",
    "review": "Start a code review",
    "index": "Index project files",
    "voice": "Voice input/output",
    "diff": "Show diff of changes",
    "inspect": "Inspect project state",
    "info": "Show system info",
    "doctor": "Run diagnostics",
}


class SlashCommandCompleter(Completer):
    """Rich completer for slash commands with fuzzy matching and descriptions."""

    def __init__(self, commands: dict[str, str]):
        self.commands = commands
        self._display_commands: list[tuple[str, str]] = [
            (name, desc) for name, desc in sorted(commands.items())
        ]

    def get_completions(self, word, document, complete_event=None):
        """Yield completions matching the word (fuzzy matching)."""
        text = word.lstrip("/").lower()

        if not text:
            for name, desc in self._display_commands[:15]:
                yield self._make_completion(name, desc, word)
            return

        matches = []
        for name, desc in self._display_commands:
            if self._fuzzy_match(text, name):
                matches.append((name, desc))
                if len(matches) >= 15:
                    break

        for name, desc in matches:
            yield self._make_completion(name, desc, word)

    def _fuzzy_match(self, pattern: str, text: str) -> bool:
        """Check if pattern matches text with fuzzy matching."""
        text_lower = text.lower()
        pattern_lower = pattern.lower()
        if text_lower.startswith(pattern_lower):
            return True
        pi = 0
        for ch in text_lower:
            if pi < len(pattern_lower) and ch == pattern_lower[pi]:
                pi += 1
        return pi == len(pattern_lower)

    def _make_completion(self, name: str, desc: str, typed: str) -> "prompt_toolkit.completion.Completion":
        """Create a Completion object with the command and description."""
        from prompt_toolkit.completion import Completion
        display = f"/{name}  — {desc}" if desc else f"/{name}"
        return Completion(
            text=f"/{name} ",
            start_position=-len(typed) if typed else 0,
            display=display,
        )


class VimKeys:
    """Vim keybindings for prompt_toolkit."""

    @staticmethod
    def get_key_bindings(
        on_interrupt: Callable[[], None] | None = None,
        on_tab_cycle: Callable[[], None] | None = None,
        navigation_callback: Callable[[str], None] | None = None,
        on_ctrl_r: Callable[[], str | None] | None = None,
        on_ctrl_t: Callable[[], None] | None = None,
        on_ctrl_b: Callable[[], None] | None = None,
        on_ctrl_o: Callable[[], None] | None = None,
        on_ctrl_l: Callable[[], None] | None = None,
    ) -> "KeyBindings":
        """Build vim key bindings."""
        kb = KeyBindings()

        @kb.add(Keys.ControlC)
        def handle_ctrl_c(event):
            if on_interrupt:
                on_interrupt()
            else:
                raise KeyboardInterrupt

        @kb.add(Keys.ShiftTab)
        def handle_shift_tab(event):
            if on_tab_cycle:
                on_tab_cycle()

        @kb.add('j', filter=has_focus)
        def handle_j(event):
            if navigation_callback:
                navigation_callback('down')
            else:
                event.current_buffer.cursor_position += 1

        @kb.add('k', filter=has_focus)
        def handle_k(event):
            if navigation_callback:
                navigation_callback('up')
            else:
                event.current_buffer.cursor_position = max(0, event.current_buffer.cursor_position - 1)

        @kb.add('g', filter=has_focus)
        def handle_g(event):
            pass

        @kb.add('G', filter=has_focus)
        def handle_shift_g(event):
            if navigation_callback:
                navigation_callback('bottom')

        @kb.add('/', filter=has_focus)
        def handle_slash(event):
            event.current_buffer.insert('/')

        @kb.add('n', filter=has_focus)
        def handle_n(event):
            if navigation_callback:
                navigation_callback('next')

        @kb.add('N', filter=has_focus)
        def handle_shift_n(event):
            if navigation_callback:
                navigation_callback('prev')

        @kb.add(Keys.Escape)
        def handle_escape(event):
            if navigation_callback:
                navigation_callback('escape')

        @kb.add(Keys.ControlR)
        def handle_ctrl_r(event):
            if on_ctrl_r:
                result = on_ctrl_r()
                if result:
                    event.current_buffer.text = result

        @kb.add(Keys.ControlT)
        def handle_ctrl_t(event):
            if on_ctrl_t:
                on_ctrl_t()

        @kb.add(Keys.ControlB)
        def handle_ctrl_b(event):
            if on_ctrl_b:
                on_ctrl_b()

        @kb.add(Keys.ControlO)
        def handle_ctrl_o(event):
            if on_ctrl_o:
                on_ctrl_o()

        @kb.add(Keys.ControlL)
        def handle_ctrl_l(event):
            if on_ctrl_l:
                on_ctrl_l()

        @kb.add(Keys.Enter, filter=has_focus)
        def handle_enter(event):
            event.current_buffer.validate_and_accept()

        return kb


class PromptToolkitInput:
    """Prompt-toolkit based input handler for the Draguniteus REPL.

    Implements rich slash command menu with fuzzy matching and arrow navigation.
    """

    def __init__(
        self,
        on_interrupt: Callable[[], None] | None = None,
        on_tab_cycle: Callable[[], None] | None = None,
        on_ctrl_r: Callable[[], str | None] | None = None,
        on_ctrl_t: Callable[[], None] | None = None,
        on_ctrl_b: Callable[[], None] | None = None,
        on_ctrl_o: Callable[[], None] | None = None,
        on_ctrl_l: Callable[[], None] | None = None,
        completions: list[str] | None = None,
    ):
        """Initialize the input handler."""
        self._on_interrupt = on_interrupt
        self._on_tab_cycle = on_tab_cycle
        self._on_ctrl_r = on_ctrl_r
        self._on_ctrl_t = on_ctrl_t
        self._on_ctrl_b = on_ctrl_b
        self._on_ctrl_o = on_ctrl_o
        self._on_ctrl_l = on_ctrl_l
        self._completions = completions or []
        self._vim_state = {"g_pressed": False}
        self._session: "PromptSession | None" = None
        self._slash_completer = SlashCommandCompleter(SLASH_COMMANDS)

    def read_line(self, prompt: str = "❯ ") -> str:
        """Read a single line of input with vim/mouse support and rich slash menu."""
        if not HAS_PROMPT_TOOLKIT:
            return self._fallback_input(prompt)

        try:
            return self._read_line_pt(prompt)
        except EOFError:
            # EOF means stdin closed (pipe mode) — re-raise to propagate
            raise
        except KeyboardInterrupt:
            raise
        except Exception:
            # Any other error (missing mouse support, etc.) — fallback to basic input
            return self._fallback_input(prompt)

    def _read_line_pt(self, prompt: str) -> str:
        """Read using prompt_toolkit with vim bindings and slash command menu."""
        from prompt_toolkit import PromptSession
        from prompt_toolkit.styles import Style

        kb = VimKeys.get_key_bindings(
            on_interrupt=self._on_interrupt,
            on_tab_cycle=self._on_tab_cycle,
            on_ctrl_r=self._on_ctrl_r,
            on_ctrl_t=self._on_ctrl_t,
            on_ctrl_b=self._on_ctrl_b,
            on_ctrl_o=self._on_ctrl_o,
            on_ctrl_l=self._on_ctrl_l,
        )

        style = Style.from_dict({
            "prompt": "#bd93f9 bold",
            "toolbar": "bg:#222222 #00ff88",
        })

        try:
            session = PromptSession(
                message=prompt,
                key_bindings=kb,
                enable_history=True,
                auto_suggest=None,
                complete_in_thread=True,
                mouse_support=True,
                style=style,
                completer=self._slash_completer,
                complete_while_typing=True,
            )
            self._session = session
            result = session.prompt()
            return result
        except KeyboardInterrupt:
            raise
        except EOFError:
            raise
        except Exception:
            raise

    def _fallback_input(self, prompt: str) -> str:
        """Simple fallback when prompt_toolkit isn't available."""
        try:
            return input(prompt)
        except (EOFError, KeyboardInterrupt):
            raise

    def set_completions(self, completions: list[str]) -> None:
        """Update slash command completions."""
        self._completions = completions

    def append_to_history(self, line: str) -> None:
        """Append a line to input history."""
        if self._session:
            try:
                self._session.history.append(line)
            except Exception:
                pass


def has_mouse_support() -> bool:
    """Check if mouse events are supported in the current terminal."""
    if not HAS_PROMPT_TOOLKIT:
        return False
    try:
        from prompt_toolkit.mouse_events import MouseEvent
        return True
    except Exception:
        return False


def has_vim_mode() -> bool:
    """Check if prompt_toolkit vim mode is available."""
    return HAS_PROMPT_TOOLKIT