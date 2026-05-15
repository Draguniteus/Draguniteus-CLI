"""Voice output — text-to-speech for spoken feedback."""
from __future__ import annotations

import io
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class VoiceSpeaker:
    """Converts text to speech and plays audio output."""

    def __init__(self, voice_id: str = "female-shaonv", model: str = "speech-02-hd"):
        self.voice_id = voice_id
        self.model = model
        self._current_process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def _get_api_key(self) -> str:
        from draguniteus.config import Config
        cfg = Config()
        return cfg.api_key

    def _speak_via_api(self, text: str, emotion: str = "happy") -> bytes | None:
        """Generate audio via MiniMax TTS API. Returns raw audio bytes or None."""
        if not HAS_REQUESTS:
            return None

        try:
            resp = requests.post(
                "https://api.minimax.io/v1/t2a_v2",
                headers={
                    "Authorization": f"Bearer {self._get_api_key()}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "text": text[:10000],  # Max 10k chars
                    "voice_id": self.voice_id,
                    "emotion": emotion,
                    "speed": 1.0,
                    "vol": 1.0,
                    "pitch": 0,
                    "format": "mp3",
                },
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                # Try various possible response shapes for audio data
                audio_b64 = ""
                # shape 1: {"data": "base64..."}
                if isinstance(data, dict):
                    for key in ("data", "audio_data", "audio", "result"):
                        val = data.get(key)
                        if isinstance(val, str) and len(val) > 100:
                            audio_b64 = val
                            break
                        elif isinstance(val, dict):
                            audio_b64 = val.get("audio_data") or val.get("audio") or ""
                            if audio_b64:
                                break
                if audio_b64:
                    import base64
                    return base64.b64decode(audio_b64)
        except Exception:
            pass
        return None

    def speak(self, text: str, emotion: str = "happy", wait: bool = True) -> bool:
        """Speak text aloud. Returns True on success."""
        with self._lock:
            self._stop()

            audio_bytes = self._speak_via_api(text, emotion)
            if not audio_bytes:
                return False

            # Write to temp file and play
            temp_path = Path.home() / ".draguniteus" / "voice_temp.mp3"
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path.write_bytes(audio_bytes)

            try:
                self._play_audio_file(temp_path, wait=wait)
                return True
            except Exception:
                return False

    def _play_audio_file(self, path: Path, wait: bool = True) -> None:
        """Play an audio file using the system default player."""
        import platform

        try:
            if platform.system() == "Windows":
                # Use PowerShell to play audio (works without extra deps)
                cmd = ["powershell", "-c", f"(New-Object System.Media.SoundPlayer('{path}')).PlaySync()"]
                self._current_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif platform.system() == "Darwin":
                self._current_process = subprocess.Popen(
                    ["afplay", str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                # Linux: try paplay, aplay, or ffplay
                for player in ["paplay", "aplay", "ffplay"]:
                    try:
                        self._current_process = subprocess.Popen(
                            [player, str(path)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        break
                    except FileNotFoundError:
                        continue

            if wait and self._current_process:
                self._current_process.wait()
        except Exception:
            pass

    def _stop(self) -> None:
        """Stop any currently playing audio."""
        if self._current_process:
            try:
                self._current_process.terminate()
                self._current_process.wait(timeout=2)
            except Exception:
                try:
                    self._current_process.kill()
                except Exception:
                    pass
            self._current_process = None

    def stop(self) -> None:
        """Stop speaking immediately."""
        with self._lock:
            self._stop()

    def speak_in_background(self, text: str, emotion: str = "happy") -> None:
        """Speak text in a background thread (non-blocking)."""
        thread = threading.Thread(target=self.speak, args=(text, emotion, True), daemon=True)
        thread.start()