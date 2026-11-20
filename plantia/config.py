"""
Configuración centralizada de rutas y constantes de PlantIA.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

APP_DATA_DIR = Path(os.getenv("PLANET_DATA_DIR", str(Path.home() / ".plantia"))).resolve()
DATABASE_PATH = APP_DATA_DIR / "plantia.db"
UPLOADS_DIR = APP_DATA_DIR / "uploads"

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

DEPRECATED_GEMINI_MODELS = {
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-lite-001",
}

AVAILABLE_GEMINI_MODELS: list[tuple[str, str]] = [
    ("gemini-2.5-flash", "Gemini 2.5 Flash (recomendado)"),
    ("gemini-2.5-flash-lite", "Gemini 2.5 Flash Lite (rápido y económico)"),
    ("gemini-3-flash-preview", "Gemini 3 Flash Preview"),
    ("gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite"),
]

ALLOWED_GEMINI_MODELS = {model_id for model_id, _ in AVAILABLE_GEMINI_MODELS}

MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_IMAGE_DIMENSION = 2048
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

PAGE_SIZE = 20


def ensure_directories() -> None:
    """Crea las carpetas necesarias si no existen."""
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def get_gemini_api_key() -> str:
    return (os.getenv("GEMINI_API_KEY") or "").strip()


def _normalize_gemini_model(model: str) -> str:
    model = (model or "").strip()
    if not model or model in DEPRECATED_GEMINI_MODELS:
        return DEFAULT_GEMINI_MODEL
    if model not in ALLOWED_GEMINI_MODELS:
        raise ValueError(
            f"Modelo no permitido: {model}. "
            f"Usa uno de: {', '.join(sorted(ALLOWED_GEMINI_MODELS))}."
        )
    return model


def get_gemini_model() -> str:
    return _normalize_gemini_model(os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL))
