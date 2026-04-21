"""
Language Detector
Identifies spoken language from transcript text.
Uses langdetect with a character-script fast-path for Devanagari/Tamil.
"""

import logging
import unicodedata

logger = logging.getLogger("2care.lang")

SUPPORTED = {"en", "hi", "ta"}


def _script_detect(text: str) -> str | None:
    """Fast script-based detection before running the ML model."""
    devanagari = sum(1 for c in text if "\u0900" <= c <= "\u097F")
    tamil = sum(1 for c in text if "\u0B80" <= c <= "\u0BFF")

    if devanagari > 3:
        return "hi"
    if tamil > 3:
        return "ta"
    return None


class LanguageDetector:
    def __init__(self):
        self._langdetect_available = False
        try:
            from langdetect import detect
            self._detect_fn = detect
            self._langdetect_available = True
        except ImportError:
            logger.warning("langdetect not installed — using script heuristic only")

    def detect(self, text: str) -> str:
        if not text.strip():
            return "en"

        # Fast path: Unicode script heuristic
        script_lang = _script_detect(text)
        if script_lang:
            logger.debug(f"🌐 Script detect: {script_lang}")
            return script_lang

        # ML fallback
        if self._langdetect_available:
            try:
                lang = self._detect_fn(text)
                # Normalise: langdetect returns 'zh-cn', 'pt' etc.
                lang = lang.split("-")[0]
                if lang in SUPPORTED:
                    logger.debug(f"🌐 ML detect: {lang}")
                    return lang
            except Exception:
                pass

        return "en"  # Safe default
