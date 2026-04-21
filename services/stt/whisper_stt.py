"""
Speech-to-Text Service
Wraps OpenAI Whisper API for fast transcription.
Falls back to a mock for testing without audio hardware.
"""

import io
import logging
import os

logger = logging.getLogger("2care.stt")


class SpeechToText:
    def __init__(self):
        self._mock = os.getenv("MOCK_STT", "false").lower() == "true"
        if not self._mock:
            try:
                import openai
                self._client = openai.AsyncOpenAI()
            except ImportError:
                logger.warning("openai not installed — using mock STT")
                self._mock = True

    async def transcribe(self, audio_bytes: bytes, hint_language: str = "en") -> str:
        """
        Transcribe raw audio bytes → text.

        hint_language: ISO 639-1 code ('en', 'hi', 'ta')
        Whisper accepts language hints which improve accuracy and speed.
        """
        if self._mock or len(audio_bytes) < 100:
            # Return canned responses for demo / tests
            return self._mock_transcribe(hint_language)

        # Map our internal codes to Whisper language codes
        lang_map = {"en": "en", "hi": "hi", "ta": "ta"}
        whisper_lang = lang_map.get(hint_language, "en")

        try:
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = "audio.webm"  # Whisper needs a filename hint

            response = await self._client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language=whisper_lang,
                response_format="text",
            )
            transcript = response.strip()
            logger.info(f"📝 STT: '{transcript}' (lang={whisper_lang})")
            return transcript

        except Exception as e:
            logger.exception(f"STT error: {e}")
            return ""

    def _mock_transcribe(self, language: str) -> str:
        samples = {
            "en": "Book an appointment with a cardiologist tomorrow at 10 AM",
            "hi": "मुझे कल कार्डियोलॉजिस्ट से अपॉइंटमेंट बुक करनी है",
            "ta": "நாளை காலை 10 மணிக்கு இதய நோய் மருத்துவரிடம் சந்திப்பு பதிவு செய்யுங்கள்",
        }
        return samples.get(language, samples["en"])
