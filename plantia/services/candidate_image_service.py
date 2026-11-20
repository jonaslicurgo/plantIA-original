from __future__ import annotations

import json
import logging
import tempfile
from threading import Lock
import urllib.parse
import urllib.request
from pathlib import Path

from plantia.config import APP_DATA_DIR, ensure_directories

_CACHE_PATH = APP_DATA_DIR / "candidate_thumbnails.json"
_CACHE_LOCK = Lock()


def _load_cache() -> dict[str, str]:
    try:
        if not _CACHE_PATH.exists():
            return {}
        data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_cache(key: str, value: str) -> None:
    try:
        with _CACHE_LOCK:
            ensure_directories()
            cache = _load_cache()
            cache[key] = value
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=APP_DATA_DIR, delete=False) as file:
                path = Path(file.name)
                try:
                    json.dump(cache, file, ensure_ascii=False)
                    file.close()
                    path.replace(_CACHE_PATH)
                finally:
                    path.unlink(missing_ok=True)
    except OSError:
        logging.getLogger(__name__).warning("Could not cache candidate thumbnail")


def get_thumbnail_url(nombre_cientifico: str) -> str:
    """
    Devuelve una miniatura (URL) para un nombre científico usando Wikipedia (REST summary).
    Si no hay imagen disponible o falla la consulta, devuelve "".
    """
    key = (nombre_cientifico or "").strip()
    if not key:
        return ""

    cache = _load_cache()
    if key in cache:
        return cache[key]

    title = key.replace(" ", "_")
    url = (
        "https://en.wikipedia.org/api/rest_v1/page/summary/"
        + urllib.parse.quote(title, safe="")
    )
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "PLANET-IA/0.1 (+https://github.com/jonaslicurgo/plantIA-original)"},
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            payload = json.loads(resp.read(256 * 1024).decode("utf-8"))
        thumb = payload.get("thumbnail", {}) or {}
        src = (thumb.get("source") or "").strip()
        if src.startswith("https://upload.wikimedia.org/"):
            _save_cache(key, src)
            return src
    except (OSError, ValueError, AttributeError):
        return ""
    return ""
