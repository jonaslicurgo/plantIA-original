"""
Gestión de sesiones y motor SQLite.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from plantia.config import DATABASE_PATH, ensure_directories
from plantia.models import Base
from plantia.utils.taxon import normalize

_engine = None
_SessionLocal = None


_PLANTAS_COLUMN_MIGRATIONS: list[tuple[str, str]] = [
    ("owner_id", "INTEGER"),
    ("encyclopedia_favorite", "INTEGER NOT NULL DEFAULT 0"),
    ("identification_cache_key", "VARCHAR(64)"),
    ("identification_cache_until", "INTEGER"),
    ("plagas_habituales", "TEXT NOT NULL DEFAULT ''"),
    ("toxicidad_perros", "TEXT NOT NULL DEFAULT ''"),
    ("toxicidad_gatos", "TEXT NOT NULL DEFAULT ''"),
    ("dificultad", "VARCHAR(64) NOT NULL DEFAULT ''"),
    ("tamano_adulto", "TEXT NOT NULL DEFAULT ''"),
    ("crecimiento", "TEXT NOT NULL DEFAULT ''"),
    ("floracion", "TEXT NOT NULL DEFAULT ''"),
    ("epoca_poda", "TEXT NOT NULL DEFAULT ''"),
    ("epoca_trasplante", "TEXT NOT NULL DEFAULT ''"),
    ("senales_trasplante", "TEXT NOT NULL DEFAULT ''"),
    ("maceta_y_sustrato", "TEXT NOT NULL DEFAULT ''"),
    ("taxonomia_reino", "VARCHAR(128) NOT NULL DEFAULT ''"),
    ("taxonomia_orden", "VARCHAR(128) NOT NULL DEFAULT ''"),
    ("taxonomia_genero", "VARCHAR(128) NOT NULL DEFAULT ''"),
    ("taxonomia_especie", "VARCHAR(128) NOT NULL DEFAULT ''"),
    ("rasgos_observados_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("preguntas_para_mejorar_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("candidatos_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("guia_inicio_json", "TEXT NOT NULL DEFAULT '{}'"),
]


def _migrate_plantas_columns(engine) -> None:
    """Añade columnas nuevas a plantas en bases de datos existentes."""
    with engine.begin() as conn:
        conn.exec_driver_sql("BEGIN IMMEDIATE")
        rows = conn.execute(text("PRAGMA table_info(plantas)")).fetchall()
        if not rows:
            return
        existing = {row[1] for row in rows}
        for name, definition in _PLANTAS_COLUMN_MIGRATIONS:
            if name not in existing:
                conn.execute(text(f"ALTER TABLE plantas ADD COLUMN {name} {definition}"))

        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_plantas_owner ON plantas(owner_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_plantas_identification ON plantas(owner_id,identification_cache_key)"))
        conn.execute(text("""CREATE TABLE IF NOT EXISTS botany_cache (
            taxon TEXT PRIMARY KEY, payload TEXT NOT NULL, expires INTEGER NOT NULL)"""))


def get_engine():
    """Inicializa lazy el motor de base de datos."""
    global _engine, _SessionLocal
    if _engine is None:
        ensure_directories()
        _engine = create_engine(
            f"sqlite:///{DATABASE_PATH}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        @event.listens_for(_engine, "connect")
        def configure_sqlite(connection, _record):
            connection.create_function("planet_normalize", 1, normalize, deterministic=True)
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(_engine)
        _migrate_plantas_columns(_engine)
        _SessionLocal = sessionmaker(
            bind=_engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
    return _engine


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Contexto de sesión con commit/rollback automático."""
    get_engine()
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_database() -> None:
    """Crea las tablas si no existen."""
    get_engine()
