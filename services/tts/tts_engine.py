"""
Text-to-Speech Service
Uses OpenAI TTS for English/Hindi; falls back to gTTS for Tamil.
Returns raw MP3 bytes suitable for WebSocket streaming.
"""

import io
import logging
import os

logger = logging.getLogger("2care.tts")

# Voice map — pick voices that sound natural per language
VOICE_MAP = {
    "en": "nova",    # OpenAI TTS voice
    "hi": "nova",
    "ta": "nova",    # gTTS handles Tamil better; OpenAI used as fallback
}


class TextToSpeech:
    def __init__(self):
        self._mock = os.getenv("MOCK_TTS", "false").lower() == "true"
        if not self._mock:
            try:
                import openai
                self._client = openai.AsyncOpenAI()
            except ImportError:
                logger.warning("openai not installed — using mock TTS")
                self._mock = True

    async def synthesize(self, text: str, language: str = "en") -> bytes:
        """Convert text to MP3 audio bytes."""
        if self._mock:
            return self._mock_audio()

        # For Tamil, prefer gTTS (better language model)
        if language == "ta":
            return await self._synthesize_gtts(text, lang="ta")

        try:
            response = await self._client.audio.speech.create(
                model="tts-1",          # tts-1 for speed; tts-1-hd for quality
                voice=VOICE_MAP.get(language, "nova"),
                input=text,
                response_format="mp3",
                speed=1.05,             # Slightly faster feels more natural
            )
            audio_bytes = response.content
            logger.debug(f"🔊 TTS synthesized {len(audio_bytes)} bytes for '{text[:40]}...'")
            return audio_bytes

        except Exception as e:
            logger.exception(f"TTS error: {e}")
            return self._mock_audio()

    async def _synthesize_gtts(self, text: str, lang: str) -> bytes:
        """Fallback TTS using gTTS (free, supports Tamil)."""
        try:
            from gtts import gTTS
            import asyncio

            def _generate():
                tts = gTTS(text=text, lang=lang, slow=False)
                buf = io.BytesIO()
                tts.write_to_fp(buf)
                return buf.getvalue()

            return await asyncio.get_event_loop().run_in_executor(None, _generate)

        except ImportError:
            logger.warning("gTTS not installed — falling back to OpenAI TTS for Tamil")
            return await self._synthesize_gtts_fallback(text)
        except Exception as e:
            logger.exception(f"gTTS error: {e}")
            return self._mock_audio()

    async def _synthesize_gtts_fallback(self, text: str) -> bytes:
        try:
            response = await self._client.audio.speech.create(
                model="tts-1",
                voice="nova",
                input=text,
                response_format="mp3",
            )
            return response.content
        except Exception:
            return self._mock_audio()

    def _mock_audio(self) -> bytes:
        """Return a tiny silent MP3 for testing without API keys."""
        # Minimal valid MP3 frame (silent)
        return b"\xff\xfb\x90\x00" + b"\x00" * 413
