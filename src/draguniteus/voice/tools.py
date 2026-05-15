"""Voice tool definitions for pair programming mode."""
from typing import Any

VOICE_TOOLS: list[dict[str, Any]] = [
    {
        "name": "voice_start",
        "description": "Start voice pair programming mode. Uses MiniMax TTS+STT to enable hands-free coding with spoken conversation and audio feedback.",
        "input_schema": {
            "type": "object",
            "properties": {
                "voice_id": {
                    "type": "string",
                    "description": "TTS voice ID to use for responses (default: female-shaonv).",
                    "default": "female-shaonv"
                },
                "model": {
                    "type": "string",
                    "description": "STT model for speech recognition (default: minimax).",
                    "default": "minimax"
                }
            }
        }
    },
    {
        "name": "voice_stop",
        "description": "Stop voice pair programming mode and return to text mode.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "voice_speak",
        "description": "Speak a message aloud using text-to-speech.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to speak."},
                "voice_id": {"type": "string", "description": "Voice ID.", "default": "female-shaonv"},
                "emotion": {"type": "string", "description": "Emotional tone (happy/calm/sad/energetic).", "default": "happy"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "voice_listen",
        "description": "Listen for spoken input and transcribe it to text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "timeout": {"type": "number", "description": "Max seconds to listen (0 = no timeout).", "default": 0}
            }
        }
    },
]