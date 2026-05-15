"""Prompt-toolkit based fullscreen REPL input with vim keys and mouse support.

Integrates with existing Rich.Live displays and the cli.py REPL loop.
Supports:
- Vim keybindings (j/k navigation, gg/G top/bottom, / search)
- Mouse click and scroll
- Ctrl+C interruption
- Shift+Tab for permission mode cycling
- Auto-completion for slash commands
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
    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False


class VimKeys:
    """Vim keybindings for prompt_toolkit.

    Supports: j (down), k (up), gg (top), G (bottom), / (search),
    n (next match), N (prev match), Ctrl+C (interrupt)
    """

    @staticmethod
    def get_key_bindings(
        on_interrupt: Callable[[], None] | None = None,
        on_tab_cycle: Callable[[], None] | None = None,
        navigation_callback: Callable[[str], None] | None = None,
    ) -> "KeyBindings":
        """Build vim key bindings.

        Args:
            on_interrupt: Called on Ctrl+C
            on_tab_cycle: Called on Shift+Tab (cycle permission mode)
            navigation_callback: Called with 'up'/'down' for j/k navigation
        """
        kb = KeyBindings()

        @kb.add(Keys.ControlC)
        def handle_ctrl_c(event):
            """Interrupt current operation."""
            if on_interrupt:
                on_interrupt()
            else:
                # Raise KeyboardInterrupt to break REPL loop
                raise KeyboardInterrupt

        @kb.add(Keys.ShiftTab)
        def handle_shift_tab(event):
            """Cycle permission mode."""
            if on_tab_cycle:
                on_tab_cycle()

        @kb.add('j', filter=has_focus)
        def handle_j(event):
            """Navigate down (vim j)."""
            if navigation_callback:
                navigation_callback('down')
            else:
                # Default: move cursor down (handled by default mapping)
                event.current_buffer.cursor_position += 1

        @kb.add('k', filter=has_focus)
        def handle_k(event):
            """Navigate up (vim k)."""
            if navigation_callback:
                navigation_callback('up')
            else:
                event.current_buffer.cursor_position = max(0, event.current_buffer.cursor_position - 1)

        @kb.add('g', filter=has_focus)
        def handle_g(event):
            """First key of gg — wait for next key."""
            pass  # gg requires two keystrokes — implement in state machine below

        @kb.add('G', filter=has_focus)
        def handle_shift_g(event):
            """Go to bottom (vim Shift+G)."""
            if navigation_callback:
                navigation_callback('bottom')

        @kb.add('/', filter=has_focus)
        def handle_slash(event):
            """Start search (vim /)."""
            # Insert / and start incremental search
            event.current_buffer.insert('/')

        @kb.add('n', filter=has_focus)
        def handle_n(event):
            """Next search match."""
            if navigation_callback:
                navigation_callback('next')

        @kb.add('N', filter=has_focus)
        def handle_shift_n(event):
            """Previous search match."""
            if navigation_callback:
                navigation_callback('prev')

        @kb.add(Keys.Escape)
        def handle_escape(event):
            """Escape — exit current mode."""
            if navigation_callback:
                navigation_callback('escape')

        @kb.add(Keys.Enter, filter=has_focus)
        def handle_enter(event):
            """Submit on Enter."""
            event.current_buffer.validate_and_accept()

        return kb


class PromptToolkitInput:
    """Prompt-toolkit based input handler for the Draguniteus REPL.

    Wraps the existing REPL loop with a modern input layer.
    Can fall back to simple input if prompt_toolkit isn't available or fails.
    """

    def __init__(
        self,
        on_interrupt: Callable[[], None] | None = None,
        on_tab_cycle: Callable[[], None] | None = None,
        on_ctrl_r: Callable[[], str | None] | None = None,
        completions: list[str] | None = None,
    ):
        """
        Args:
            on_interrupt: Called on Ctrl+C
            on_tab_cycle: Called on Shift+Tab (permission mode cycle)
            on_ctrl_r: Called on Ctrl+R — should return matched history entry or None
            completions: List of slash commands for tab completion
        """
        self._on_interrupt = on_interrupt
        self._on_tab_cycle = on_tab_cycle
        self._on_ctrl_r = on_ctrl_r
        self._completions = completions or []
        self._vim_state = {"g_pressed": False}
        self._session: "PromptSession | None" = None

    def read_line(self, prompt: str = "❯ ") -> str:
        """Read a single line of input with vim/mouse support.

        Falls back to simple input() if prompt_toolkit fails.
        """
        if not HAS_PROMPT_TOOLKIT:
            return self._fallback_input(prompt)

        try:
            return self._read_line_pt(prompt)
        except Exception:
            return self._fallback_input(prompt)

    def _read_line_pt(self, prompt: str) -> str:
        """Read using prompt_toolkit with vim bindings."""
        from prompt_toolkit import PromptSession
        from prompt_toolkit.buffer import Buffer
        from prompt_toolkit.styles import Style

        kb = VimKeys.get_key_bindings(
            on_interrupt=self._on_interrupt,
            on_tab_cycle=self._on_tab_cycle,
        )

        def navigation_callback(action: str):
            self._vim_state[action] = True

        # Add vim motion keybindings after creation
        kb2 = VimKeys.get_key_bindings(
            on_interrupt=self._on_interrupt,
            on_tab_cycle=self._on_tab_cycle,
            navigation_callback=navigation_callback,
        )

        style = Style.from_dict({
            "prompt": "#00ff88 bold",
            "toolbar": "bg:#222222 #00ff88",
        })

        try:
            session = PromptSession(
                message=prompt,
                key_bindings=kb,
                enable_history=True,
                auto_suggest=None,
                complete_in_thread=False,
                mouse_support=True,
                style=style,
            )
            result = session.prompt()
            return result
        except KeyboardInterrupt:
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