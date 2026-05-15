"""MiniMax Token Plan tools: TTS, image generation, video, music, voice cloning."""
from __future__ import annotations

import json
import os
import base64
from pathlib import Path
from typing import Any

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


MINIMAX_TOOLS: list[dict[str, Any]] = [
    {
        "name": "text_to_audio",
        "description": "Convert text to natural speech using MiniMax TTS API. Saves audio file to output_directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to synthesize (max 10,000 chars). Use \\n for paragraphs."},
                "output_directory": {"type": "string", "description": "Directory to save audio files."},
                "voice_id": {"type": "string", "description": "Voice ID to use.", "default": "female-shaonv"},
                "model": {"type": "string", "description": "Model version.", "default": "speech-02-hd"},
                "speed": {"type": "number", "description": "Speed adjustment (0.5-2.0).", "default": 1.0},
                "vol": {"type": "number", "description": "Volume (0-10).", "default": 1.0},
                "pitch": {"type": "integer", "description": "Pitch adjustment (-12 to 12).", "default": 0},
                "emotion": {"type": "string", "description": "Emotional tone.", "default": "happy"},
                "format": {"type": "string", "description": "Output format (mp3/wav/pcm/flac).", "default": "mp3"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "list_voices",
        "description": "List all available TTS voices from MiniMax.",
        "input_schema": {
            "type": "object",
            "properties": {
                "voice_type": {"type": "string", "description": "Voice type to query (system/voice_cloning/voice_generation/music_generation/all).", "default": "all"}
            }
        }
    },
    {
        "name": "voice_clone",
        "description": "Clone a voice from an audio file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "voice_id": {"type": "string", "description": "ID for the cloned voice (8-256 chars, letter start, letters/digits/-/_ only)."},
                "file": {"type": "string", "description": "Audio file to clone from (mp3/m4a/wav)."},
                "text": {"type": "string", "description": "Demo text (max 2000 chars)."},
                "output_directory": {"type": "string", "description": "Directory to save audio files."}
            },
            "required": ["voice_id", "file"]
        }
    },
    {
        "name": "text_to_image",
        "description": "Generate images from a text prompt using MiniMax image generation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Image description (max 1500 chars)."},
                "model": {"type": "string", "description": "Model version (image-01/image-01-live).", "default": "image-01"},
                "aspect_ratio": {"type": "string", "description": "Aspect ratio (1:1/16:9/4:3/3:2/2:3/3:4/9:16/21:9).", "default": "1:1"},
                "n": {"type": "integer", "description": "Number of images (1-9).", "default": 1},
                "output_directory": {"type": "string", "description": "Directory to save images."}
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "generate_video",
        "description": "Generate video from text prompt or first-frame image using MiniMax Hailuo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Video description (max 2000 chars)."},
                "model": {"type": "string", "description": "Model (MiniMax-Hailuo-02/T2V-01-Director/I2V-01-Director/S2V-01/I2V-01-live/I2V-01/T2V-01).", "default": "T2V-01"},
                "first_frame_image": {"type": "string", "description": "First frame as base64 or URL."},
                "duration": {"type": "integer", "description": "Duration 6 or 10 seconds.", "default": 6},
                "resolution": {"type": "string", "description": "Resolution (512P/768P/1080P)."},
                "output_directory": {"type": "string", "description": "Directory to save videos."},
                "async_mode": {"type": "boolean", "description": "Async mode returns task ID.", "default": False}
            }
        }
    },
    {
        "name": "music_generation",
        "description": "Generate music from prompt and lyrics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Music inspiration (10-300 chars)."},
                "lyrics": {"type": "string", "description": "Lyrics separated by \\n. Supports [Intro]/[Verse]/[Chorus]/[Bridge]/[Outro] (10-600 chars)."},
                "sample_rate": {"type": "integer", "description": "Sample rate.", "default": 32000},
                "bitrate": {"type": "integer", "description": "Bitrate.", "default": 128000},
                "format": {"type": "string", "description": "Format (mp3/wav/pcm).", "default": "mp3"},
                "output_directory": {"type": "string", "description": "Directory to save music."}
            },
            "required": ["prompt", "lyrics"]
        }
    },
    {
        "name": "query_video_generation",
        "description": "Query status of async video generation task.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID from async video generation."},
                "output_directory": {"type": "string", "description": "Directory to save videos."}
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "image_to_video",
        "description": "Generate video from first-frame image.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Video description (max 2000 chars)."},
                "model": {"type": "string", "description": "Model version.", "default": "T2V-01"},
                "first_frame_image": {"type": "string", "description": "First frame as base64 or URL."},
                "output_directory": {"type": "string", "description": "Directory to save videos."},
                "async_mode": {"type": "boolean", "description": "Async mode.", "default": False}
            }
        }
    },
]


def _get_minimax_api_key() -> str:
    """Get MiniMax API key from config."""
    from draguniteus.config import Config
    cfg = Config()
    return cfg.api_key


def _minimax_api_headers() -> dict:
    """Build headers for MiniMax API calls."""
    return {
        "Authorization": f"Bearer {_get_minimax_api_key()}",
        "Content-Type": "application/json"
    }


def tool_text_to_audio(
    text: str,
    output_directory: str | None = None,
    voice_id: str = "female-shaonv",
    model: str = "speech-02-hd",
    speed: float = 1.0,
    vol: float = 1.0,
    pitch: int = 0,
    emotion: str = "happy",
    format: str = "mp3"
) -> str:
    """Convert text to speech via MiniMax API."""
    if output_directory is None:
        output_directory = str(Path.home() / "Downloads")

    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)
    import time
    filename = f"tts_{int(time.time())}.{format}"
    filepath = output_path / filename

    try:
        resp = requests.post(
            "https://api.minimax.io/v1/t2a_v2",
            headers=_minimax_api_headers(),
            json={
                "model": model,
                "text": text,
                "voice_id": voice_id,
                "speed": speed,
                "vol": vol,
                "pitch": pitch,
                "emotion": emotion,
                "output_file": str(filepath),
                "audio_format": format
            },
            timeout=60
        )
        if resp.status_code == 200:
            return f"ok — saved to {filepath}"
        else:
            return f"MiniMax TTS error: {resp.status_code} {resp.text[:500]}"
    except Exception as e:
        return f"text_to_audio error: {e}"


def tool_list_voices(voice_type: str = "all") -> str:
    """List available TTS voices."""
    try:
        resp = requests.get(
            "https://api.minimax.io/v1/voices",
            headers=_minimax_api_headers(),
            timeout=30
        )
        if resp.status_code == 200:
            return json.dumps(resp.json(), indent=2)
        else:
            return f"list_voices error: {resp.status_code}"
    except Exception as e:
        return f"list_voices error: {e}"


def tool_voice_clone(
    voice_id: str,
    file: str,
    text: str | None = None,
    output_directory: str | None = None,
    is_url: bool = False
) -> str:
    """Clone a voice from audio file."""
    try:
        resp = requests.post(
            "https://api.minimax.io/v1/voice_clone",
            headers=_minimax_api_headers(),
            json={
                "voice_id": voice_id,
                "source": file,
                "text": text or "",
                "is_url": is_url
            },
            timeout=60
        )
        if resp.status_code == 200:
            return f"ok — voice cloned: {voice_id}"
        else:
            return f"voice_clone error: {resp.status_code} {resp.text[:500]}"
    except Exception as e:
        return f"voice_clone error: {e}"


def tool_text_to_image(
    prompt: str,
    model: str = "image-01",
    aspect_ratio: str = "1:1",
    n: int = 1,
    prompt_optimizer: bool = True,
    output_directory: str | None = None
) -> str:
    """Generate images via MiniMax."""
    if output_directory is None:
        output_directory = str(Path.home() / "Downloads")

    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)

    try:
        resp = requests.post(
            "https://api.minimax.io/v1/image_generation",
            headers=_minimax_api_headers(),
            json={
                "model": model,
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "n": n,
                "prompt_optimizer": prompt_optimizer
            },
            timeout=120
        )
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("data", [])
            saved = []
            for i, item in enumerate(results):
                img_data = item.get("base64_image") or item.get("image_url", "")
                if img_data:
                    filename = f"img_{i}_{int(time.time())}.png"
                    filepath = output_path / filename
                    if item.get("base64_image"):
                        with open(filepath, "wb") as f:
                            f.write(base64.b64decode(img_data))
                    saved.append(str(filepath))
            if saved:
                return f"ok — saved {len(saved)} image(s): {', '.join(saved)}"
            return json.dumps(data, indent=2)
        else:
            return f"text_to_image error: {resp.status_code} {resp.text[:500]}"
    except Exception as e:
        return f"text_to_image error: {e}"


def tool_generate_video(
    prompt: str | None = None,
    model: str = "T2V-01",
    first_frame_image: str | None = None,
    duration: int = 6,
    resolution: str | None = None,
    output_directory: str | None = None,
    async_mode: bool = False
) -> str:
    """Generate video via MiniMax Hailuo."""
    if output_directory is None:
        output_directory = str(Path.home() / "Downloads")

    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "model": model,
        "duration": duration,
        "async_mode": async_mode
    }
    if prompt:
        payload["prompt"] = prompt
    if first_frame_image:
        payload["first_frame_image"] = first_frame_image
    if resolution:
        payload["resolution"] = resolution

    try:
        resp = requests.post(
            "https://api.minimax.io/v1/video_generation",
            headers=_minimax_api_headers(),
            json=payload,
            timeout=60
        )
        if resp.status_code == 200:
            data = resp.json()
            if async_mode:
                task_id = data.get("task_id", "")
                return f"ok — async task started: {task_id}"
            else:
                video_url = data.get("video_url", "")
                return f"ok — video generated: {video_url}"
        else:
            return f"generate_video error: {resp.status_code} {resp.text[:500]}"
    except Exception as e:
        return f"generate_video error: {e}"


def tool_music_generation(
    prompt: str,
    lyrics: str,
    sample_rate: int = 32000,
    bitrate: int = 128000,
    format: str = "mp3",
    output_directory: str | None = None
) -> str:
    """Generate music via MiniMax."""
    if output_directory is None:
        output_directory = str(Path.home() / "Downloads")

    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)

    try:
        resp = requests.post(
            "https://api.minimax.io/v1/music_generation",
            headers=_minimax_api_headers(),
            json={
                "prompt": prompt,
                "lyrics": lyrics,
                "sample_rate": sample_rate,
                "bitrate": bitrate,
                "format": format
            },
            timeout=120
        )
        if resp.status_code == 200:
            data = resp.json()
            music_url = data.get("music_url", "")
            return f"ok — music generated: {music_url}"
        else:
            return f"music_generation error: {resp.status_code} {resp.text[:500]}"
    except Exception as e:
        return f"music_generation error: {e}"


def tool_query_video_generation(
    task_id: str,
    output_directory: str | None = None
) -> str:
    """Query async video generation status."""
    try:
        resp = requests.get(
            f"https://api.minimax.io/v1/video_generation/{task_id}",
            headers=_minimax_api_headers(),
            timeout=30
        )
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("status", "")
            if status == "completed":
                video_url = data.get("video_url", "")
                return f"completed — {video_url}"
            elif status == "failed":
                return f"failed — {data.get('error', 'unknown error')}"
            else:
                return f"status: {status}"
        else:
            return f"query_video_generation error: {resp.status_code}"
    except Exception as e:
        return f"query_video_generation error: {e}"


def tool_image_to_video(
    prompt: str | None = None,
    model: str = "T2V-01",
    first_frame_image: str | None = None,
    output_directory: str | None = None,
    async_mode: bool = False
) -> str:
    """Generate video from first-frame image."""
    if output_directory is None:
        output_directory = str(Path.home() / "Downloads")

    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "model": model,
        "async_mode": async_mode
    }
    if prompt:
        payload["prompt"] = prompt
    if first_frame_image:
        payload["first_frame_image"] = first_frame_image

    try:
        resp = requests.post(
            "https://api.minimax.io/v1/video_generation",
            headers=_minimax_api_headers(),
            json=payload,
            timeout=60
        )
        if resp.status_code == 200:
            data = resp.json()
            if async_mode:
                return f"ok — task: {data.get('task_id', '')}"
            return f"ok — video: {data.get('video_url', '')}"
        else:
            return f"image_to_video error: {resp.status_code} {resp.text[:500]}"
    except Exception as e:
        return f"image_to_video error: {e}"
