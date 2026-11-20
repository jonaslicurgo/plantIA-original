"""Web locale negotiation and translation catalog."""

from functools import lru_cache
from pathlib import Path
import json

LANGUAGES = {
    "pt-BR": ("Português (Brasil)", "Brazilian Portuguese"),
    "en": ("English", "English"),
    "es": ("Español", "Spanish"),
    "fr": ("Français", "French"),
    "de": ("Deutsch", "German"),
    "it": ("Italiano", "Italian"),
    "hi": ("हिन्दी", "Hindi"),
    "id": ("Bahasa Indonesia", "Indonesian"),
    "ar": ("العربية", "Arabic"),
    "ja": ("日本語", "Japanese"),
    "ko": ("한국어", "Korean"),
    "zh-Hans": ("简体中文", "Simplified Chinese"),
}


def locale_for(request):
    preference = request.cookies.get("planet_language")
    if preference in LANGUAGES:
        return preference
    weighted = []
    aliases = {code.split("-")[0]: code for code in LANGUAGES}
    for item in request.headers.get("accept-language", "")[:2048].split(","):
        tag, _, weight = item.strip().lower().partition(";q=")
        try:
            score = float(weight) if weight else 1
        except ValueError:
            continue
        code = aliases.get(tag.split("-")[0])
        if code and 0 < score <= 1:
            weighted.append((score, code))
    return max(weighted, key=lambda pair: pair[0])[1] if weighted else "pt-BR"


@lru_cache(maxsize=len(LANGUAGES))
def catalog(locale):
    path = Path(__file__).with_name("locales") / f"{locale}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def translations(request):
    locale = locale_for(request)
    messages = catalog(locale)
    return {"locale": locale, "languages": LANGUAGES,
            "tr": lambda key: messages.get(key, key),
            "rtl": locale == "ar"}
