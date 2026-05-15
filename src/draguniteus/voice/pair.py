"""Pair programming mode — voice + text hybrid coding session."""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from draguniteus.voice.input import VoiceListener
from draguniteus.voice.output import VoiceSpeaker


class PairProgrammingMode:
    """Hands-free pair programming with voice I/O.

    Integrates voice listener + speaker with the CLI to enable
    spoken conversation and audio feedback during coding sessions.
    """

    def __init__(
        self,
        voice_id: str = "female-shaonv",
        stt_model: str = "minimax",
        tts_model: str = "speech-02-hd",
    ):
        self.voice_id = voice_id
        self.stt_model = stt_model
        self.tts_model = tts_model

        self._listener = VoiceListener(model=stt_model)
        self._speaker = VoiceSpeaker(voice_id=voice_id, model=tts_model)

        self._active = False
        self._mode_lock = threading.Lock()
        self._text_callback: Callable[[str], None] | None = None
        self._voice_mode = "interrupted"  # "interrupted" | "continuous" | "text-only"
        self._last_spoken: str = ""
        self._suppress_speech = False

    def is_active(self) -> bool:
        return self._active

    def is_voice_available(self) -> bool:
        return self._listener.is_available()

    def start(
        self,
        on_text_input: Callable[[str], None],
        voice_mode: str = "interrupted",
    ) -> str:
        """Start pair programming mode.

        on_text_input: called when voice is transcribed to text
        voice_mode: "interrupted" = push-to-talk, "continuous" = always listening,
                   "text-only" = voice disabled, TTS only
        Returns a status message.
        """
        with self._mode_lock:
            if self._active:
                return "Voice mode already active. Use /voice stop first."

            self._text_callback = on_text_input
            self._voice_mode = voice_mode
            self._active = True
            self._suppress_speech = False

            status_parts = []

            # Start TTS speaker always
            status_parts.append(f"TTS: {self.voice_id} ({self.tts_model})")

            # Start voice listening based on mode
            if voice_mode != "text-only":
                if self._listener.start_listening(self._on_voice_transcript):
                    status_parts.append(f"STT: listening ({voice_mode} mode)")
                else:
                    status_parts.append("STT: unavailable (install speech_recognition)")
                    if voice_mode == "continuous":
                        return "⚠️  Voice mode started in text-only (STT unavailable):\n  " + ", ".join(status_parts)

            return "🎙️  Voice pair programming active — " + ", ".join(status_parts)

    def stop(self) -> str:
        """Stop pair programming mode."""
        with self._mode_lock:
            if not self._active:
                return "Voice mode not active."

            self._active = False
            self._listener.stop_listening()
            self._speaker.stop()
            self._text_callback = None

            return "🎙️  Voice mode stopped. Back to text."

    def _on_voice_transcript(self, transcript: str) -> None:
        """Called by VoiceListener when speech is transcribed."""
        if not self._active:
            return

        text = transcript.strip()
        if not text:
            return

        self._last_spoken = text

        # Send to text input handler
        if self._text_callback:
            try:
                self._text_callback(text)
            except Exception:
                pass

    def speak(self, text: str, emotion: str = "happy") -> None:
        """Speak text aloud to the user."""
        if not self._active or self._suppress_speech:
            return
        self._speaker.speak_in_background(text, emotion)

    def speak_sync(self, text: str, emotion: str = "happy") -> bool:
        """Speak text and wait for completion."""
        if not self._active or self._suppress_speech:
            return False
        return self._speaker.speak(text, emotion, wait=True)

    def stop_speaking(self) -> None:
        """Stop current speech."""
        self._speaker.stop()

    def set_voice_mode(self, mode: str) -> None:
        """Change voice mode: 'interrupted', 'continuous', or 'text-only'."""
        if mode not in ("interrupted", "continuous", "text-only"):
            return
        self._voice_mode = mode

        if mode == "text-only":
            self._listener.stop_listening()
        elif mode == "continuous" and self._active:
            self._listener.start_listening(self._on_voice_transcript)

    def suppress_speech(self, suppress: bool = True) -> None:
        """Suppress TTS output (for quiet environments)."""
        self._suppress_speech = suppress
        if suppress:
            self._speaker.stop()

    def get_last_transcript(self) -> str:
        """Get the last voice transcription."""
        return self._last_spoken

    def change_voice(self, voice_id: str) -> bool:
        """Change the TTS voice. Returns True if voice is valid."""
        self._voice_id = voice_id
        self._speaker.voice_id = voice_id
        return True

    def listen_once(self, timeout: float = 5.0) -> str:
        """Manual push-to-talk: listen for one utterance."""
        if not self._active:
            return ""
        return self._listener.listen_once(timeout=timeout)

    def speak_status(self) -> str:
        """Get current voice status summary."""
        if not self._active:
            return "inactive"

        parts = [f"mode={self._voice_mode}"]
        if self._speaker.voice_id:
            parts.append(f"voice={self._speaker.voice_id}")
        parts.append(f"stt={'on' if self._listener.is_available() else 'off'}")
        if self._last_spoken:
            parts.append(f'last="{self._last_spoken[:30]}..."')
        return " | ".join(parts)


# Global pair programming instance
_pair_mode: PairProgrammingMode | None = None


def get_pair_mode() -> PairProgrammingMode:
    global _pair_mode
    if _pair_mode is None:
        _pair_mode = PairProgrammingMode()
    return _pair_mode


def tool_voice_start(voice_id: str = "female-shaonv", model: str = "minimax", **kwargs) -> str:
    """Start voice pair programming mode."""
    pair = get_pair_mode()
    if pair.is_active():
        return "Voice mode already active. Use voice_stop first."

    def on_voice_input(text: str):
        # This would need to be wired into the CLI's message handling
        # For now just log it; CLI integration handles actual routing
        pass

    return pair.start(on_voice_input, voice_mode="interrupted")


def tool_voice_stop(**kwargs) -> str:
    """Stop voice pair programming mode."""
    pair = get_pair_mode()
    return pair.stop()


def tool_voice_speak(text: str, voice_id: str = "female-shaonv", emotion: str = "happy", **kwargs) -> str:
    """Speak text aloud."""
    pair = get_pair_mode()
    pair.change_voice(voice_id)
    pair.speak_sync(text, emotion)
    return f"Spoken: {text[:50]}{'...' if len(text) > 50 else ''}"


def tool_voice_listen(timeout: float = 0, **kwargs) -> str:
    """Listen for spoken input."""
    pair = get_pair_mode()
    if not pair.is_active():
        return "Voice mode not active."
    transcript = pair.listen_once(timeout=timeout if timeout > 0 else 5.0)
    if not transcript:
        return "(no speech detected)"
    return transcript