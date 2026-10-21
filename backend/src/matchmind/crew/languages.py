"""The languages a viewer can pick and where each one's text comes from.

- Studio languages (en, es, fr, ar, ja): hand-written phrase packs, always on.
- World languages (pt, de, hi, zh-Hans, sw, id, tr, ko): the crew's English
  text translated by Azure AI Translator, then fact-checked again. Only
  available when the translator switch is on; otherwise shown in English.
"""

from __future__ import annotations

from matchmind.crew.contracts import (
    LANGUAGES,
    RTL_LANGUAGES,
    STUDIO_LANGUAGES,
    LanguageInfo,
)

# (own name, English name)
NAMES: dict[str, tuple[str, str]] = {
    "en": ("English", "English"),
    "es": ("Español", "Spanish"),
    "fr": ("Français", "French"),
    "ar": ("العربية", "Arabic"),
    "ja": ("日本語", "Japanese"),
    "pt": ("Português", "Portuguese"),
    "de": ("Deutsch", "German"),
    "hi": ("हिन्दी", "Hindi"),
    "zh-Hans": ("简体中文", "Chinese (Simplified)"),
    "sw": ("Kiswahili", "Swahili"),
    "id": ("Bahasa Indonesia", "Indonesian"),
    "tr": ("Türkçe", "Turkish"),
    "ko": ("한국어", "Korean"),
}


def language_list(translator_available: bool) -> list[LanguageInfo]:
    """Every language, studio packs first, with whether it can be shown now."""
    out: list[LanguageInfo] = []
    for code in LANGUAGES:
        studio = code in STUDIO_LANGUAGES
        available = studio or translator_available
        own, english = NAMES[code]
        out.append(
            LanguageInfo(
                code=code,
                name=own,
                english_name=english,
                source="studio" if studio else "translator",
                available=available,
                rtl=code in RTL_LANGUAGES,
                reason=None if available else "translator_off",
            )
        )
    return out
