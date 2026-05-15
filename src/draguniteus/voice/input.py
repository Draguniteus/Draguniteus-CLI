"""Voice input — microphone capture and speech-to-text."""
from __future__ import annotations

import io
import wave
import threading
import time
from typing import Callable

try:
    import speech_recognition as sr
    HAS_SR = True
except ImportError:
    HAS_SR = False

try:
    import pyaudio
    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False


class VoiceListener:
    """Captures microphone audio and transcribes to text using STT."""

    def __init__(self, model: str = "minimax", energy_threshold: int = 300):
        self.model = model
        self.energy_threshold = energy_threshold
        self._recognizer = sr.Recognizer() if HAS_SR else None
        self._microphone = sr.Microphone() if HAS_SR else None
        self._listening = False
        self._listen_thread: threading.Thread | None = None
        self._callback: Callable[[str], None] | None = None
        self._last_transcript = ""
        self._stop_signal = threading.Event()

        if HAS_SR and self._recognizer:
            self._recognizer.energy_threshold = energy_threshold
            self._recognizer.pause_threshold = 0.8

    def is_available(self) -> bool:
        """Check if speech recognition is available."""
        if not HAS_SR or not self._recognizer:
            return False
        # Verify microphone is also accessible
        if not HAS_PYAUDIO or not self._microphone:
            # speech_recognition still works with default mic on some platforms
            pass
        return self._recognizer is not None

    def availability_reason(self) -> str:
        """Return a human-readable reason if voice is unavailable."""
        if HAS_SR:
            if HAS_PYAUDIO:
                return "ready"
            return "microphone (pyaudio) not installed — speech_recognition available"
        if not HAS_REQUESTS:
            return "requests library not installed"
        return "speech_recognition not installed — run: pip install SpeechRecognition"

    def start_listening(self, callback: Callable[[str], None]) -> bool:
        """Start background listening with callback for transcriptions."""
        if not self.is_available():
            return False

        self._callback = callback
        self._stop_signal.clear()
        self._listening = True
        self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listen_thread.start()
        return True

    def stop_listening(self) -> None:
        """Stop background listening."""
        self._listening = False
        self._stop_signal.set()
        if self._listen_thread:
            self._listen_thread.join(timeout=2.0)
            self._listen_thread = None

    def _listen_loop(self) -> None:
        """Background loop that listens for speech and calls callback."""
        if not HAS_SR or not self._recognizer or not self._microphone:
            return

        try:
            with self._microphone as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
                while self._listening and not self._stop_signal.is_set():
                    try:
                        audio = self._recognizer.listen(
                            source,
                            timeout=5.0,
                            phrase_time_limit=30
                        )
                        transcript = self._recognize(audio)
                        if transcript and self._callback:
                            self._callback(transcript)
                    except sr.WaitTimeoutError:
                        continue
                    except Exception:
                        if not self._listening:
                            break
        except Exception:
            pass

    def _recognize(self, audio: "sr.AudioData") -> str:
        """Transcribe audio using the configured STT backend."""
        if not HAS_SR or not self._recognizer:
            return ""

        try:
            # Try Google Speech Recognition first (free tier)
            # Falls back to other services
            try:
                text = self._recognizer.recognize_google(audio, language="en-US")
                return text
            except sr.UnknownValueError:
                return ""
            except sr.RequestError:
                pass

            # MiniMax STT via API if available
            try:
                import requests
                from draguniteus.config import Config
                cfg = Config()
                audio_data = audio.get_raw_data(convert_rate=16000, convert_width=2)
                resp = requests.post(
                    "https://api.minimax.io/v1/asr",
                    headers={"Authorization": f"Bearer {cfg.api_key}"},
                    files={"audio": ("audio.wav", io.BytesIO(audio_data), "audio/wav")},
                    data={"model": self.model},
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("text", "")
            except Exception:
                pass

            return ""
        except Exception:
            return ""

    def listen_once(self, timeout: float = 5.0) -> str:
        """Listen for a single utterance and return transcription."""
        if not self.is_available():
            return ""

        try:
            with self._microphone as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self._recognizer.listen(source, timeout=timeout, phrase_time_limit=30)
                return self._recognize(audio)
        except Exception:
            return ""

    def set_energy_threshold(self, threshold: int) -> None:
        """Update the energy threshold for voice activation."""
        if self._recognizer:
            self._recognizer.energy_threshold = threshold