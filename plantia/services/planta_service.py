"""
Servicio de gestión de plantas identificadas.
"""

from __future__ import annotations

import json
import uuid
from time import time
from dataclasses import dataclass
from pathlib import Path
import logging

from sqlalchemy import func, or_, select, update

from plantia.config import PAGE_SIZE, UPLOADS_DIR, ensure_directories
from plantia.database import session_scope
from plantia.models import Planta
from plantia.schemas.planta import IdentificacionGemini, PlantaCreate
from plantia.services.candidate_image_service import get_thumbnail_url
from plantia.services.botany import SPECIES
from plantia.utils.taxon import normalize


@dataclass
class PaginaPlantas:
    items: list[Planta]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        if self.total == 0:
            return 1
        return (self.total + self.page_size - 1) // self.page_size


class PlantaService:
    """Operaciones CRUD sobre plantas identificadas."""

    @staticmethod
    def guardar_imagen(image_bytes: bytes, extension: str) -> str:
        """Guarda la imagen en disco y devuelve la ruta absoluta."""
        ensure_directories()
        ext = extension.lstrip(".").lower()
        if ext not in ("jpg", "jpeg", "png", "webp"):
            ext = "jpg"
        filename = f"{uuid.uuid4().hex}.{ext}"
        path = UPLOADS_DIR / filename
        path.write_bytes(image_bytes)
        return str(path)

    @staticmethod
    def crear_desde_identificacion(
        identificacion: IdentificacionGemini, image_path: str, owner_id: int, cache_key: str | None = None
    ) -> Planta:
        # Enriquecer candidatos con miniaturas (si es posible)
        candidatos = []
        for cand in identificacion.candidatos[:3]:
            cand.thumbnail_url = get_thumbnail_url(cand.nombre_cientifico) if cand.nombre_cientifico else ""
            candidatos.append(cand.model_dump())

        datos = PlantaCreate(
            nombre_comun=identificacion.nombre_comun,
            nombre_cientifico=identificacion.nombre_cientifico,
            familia=identificacion.familia or identificacion.taxonomia.familia,
            tipo=identificacion.tipo,
            descripcion=identificacion.descripcion,
            riego=identificacion.cuidados.riego,
            luz=identificacion.cuidados.luz,
            temperatura=identificacion.cuidados.temperatura,
            humedad=identificacion.cuidados.humedad,
            suelo=identificacion.cuidados.suelo,
            fertilizacion=identificacion.cuidados.fertilizacion,
            problemas_comunes=identificacion.cuidados.problemas_comunes,
            plagas_habituales=identificacion.cuidados.plagas_habituales,
            toxicidad_perros="",
            toxicidad_gatos="",
            dificultad=identificacion.caracteristicas.dificultad,
            tamano_adulto=identificacion.caracteristicas.tamano_adulto,
            crecimiento=identificacion.caracteristicas.crecimiento,
            floracion=identificacion.caracteristicas.floracion,
            epoca_poda=identificacion.caracteristicas.epoca_poda,
            epoca_trasplante=identificacion.caracteristicas.epoca_trasplante,
            senales_trasplante=identificacion.caracteristicas.senales_trasplante,
            maceta_y_sustrato=identificacion.caracteristicas.maceta_y_sustrato,
            taxonomia_reino=identificacion.taxonomia.reino,
            taxonomia_orden=identificacion.taxonomia.orden,
            taxonomia_genero=identificacion.taxonomia.genero,
            taxonomia_especie=identificacion.taxonomia.especie,
            rasgos_observados_json=json.dumps(
                identificacion.rasgos_observados, ensure_ascii=False
            ),
            preguntas_para_mejorar_json=json.dumps(
                identificacion.preguntas_para_mejorar, ensure_ascii=False
            ),
            candidatos_json=json.dumps(candidatos, ensure_ascii=False),
            guia_inicio_json=json.dumps(
                identificacion.guia_inicio.model_dump(), ensure_ascii=False
            ),
            confianza=identificacion.confianza,
            image_path=image_path,
        )
        return PlantaService.crear(datos, owner_id, cache_key)

    @staticmethod
    def crear(datos: PlantaCreate, owner_id: int, cache_key: str | None = None) -> Planta:
        with session_scope() as session:
            planta = Planta(
                owner_id=owner_id,
                identification_cache_key=cache_key,
                identification_cache_until=int(time()) + 86400 if cache_key else None,
                image_path=datos.image_path,
                nombre_comun=datos.nombre_comun.strip(),
                nombre_cientifico=datos.nombre_cientifico.strip(),
                familia=datos.familia.strip(),
                tipo=datos.tipo.strip(),
                descripcion=datos.descripcion.strip(),
                riego=datos.riego.strip(),
                luz=datos.luz.strip(),
                temperatura=datos.temperatura.strip(),
                humedad=datos.humedad.strip(),
                suelo=datos.suelo.strip(),
                fertilizacion=datos.fertilizacion.strip(),
                problemas_comunes=datos.problemas_comunes.strip(),
                plagas_habituales=datos.plagas_habituales.strip(),
                toxicidad_perros=datos.toxicidad_perros.strip(),
                toxicidad_gatos=datos.toxicidad_gatos.strip(),
                dificultad=datos.dificultad.strip(),
                tamano_adulto=datos.tamano_adulto.strip(),
                crecimiento=datos.crecimiento.strip(),
                floracion=datos.floracion.strip(),
                epoca_poda=datos.epoca_poda.strip(),
                epoca_trasplante=datos.epoca_trasplante.strip(),
                senales_trasplante=datos.senales_trasplante.strip(),
                maceta_y_sustrato=datos.maceta_y_sustrato.strip(),
                taxonomia_reino=datos.taxonomia_reino.strip(),
                taxonomia_orden=datos.taxonomia_orden.strip(),
                taxonomia_genero=datos.taxonomia_genero.strip(),
                taxonomia_especie=datos.taxonomia_especie.strip(),
                rasgos_observados_json=datos.rasgos_observados_json.strip() or "[]",
                preguntas_para_mejorar_json=datos.preguntas_para_mejorar_json.strip()
                or "[]",
                candidatos_json=datos.candidatos_json.strip() or "[]",
                guia_inicio_json=datos.guia_inicio_json.strip() or "{}",
                confianza=datos.confianza.strip(),
            )
            session.add(planta)
            session.flush()
            session.refresh(planta)
            return planta

    @staticmethod
    def find_cached_identification(owner_id: int, cache_key: str) -> Planta | None:
        with session_scope() as session:
            return session.scalar(select(Planta).where(
                Planta.owner_id == owner_id,
                Planta.identification_cache_key == cache_key,
                Planta.identification_cache_until > int(time()),
            ).order_by(Planta.id.desc()).limit(1))

    @staticmethod
    def obtener_por_id(planta_id: int, owner_id: int) -> Planta | None:
        with session_scope() as session:
            return session.scalar(select(Planta).where(Planta.id == planta_id, Planta.owner_id == owner_id))

    # Órdenes admitidos para el listado de plantas.
    ORDENES_VALIDOS = ("recientes", "antiguas", "nombre", "confianza")

    @staticmethod
    def _clausula_orden(orden: str):
        from sqlalchemy import case

        if orden == "antiguas":
            return (Planta.created_at.asc(),)
        if orden == "nombre":
            return (func.lower(Planta.nombre_comun).asc(),)
        if orden == "confianza":
            # alto > medio > bajo, y a igualdad, más recientes primero.
            prioridad = case(
                (Planta.confianza == "alto", 0),
                (Planta.confianza == "medio", 1),
                (Planta.confianza == "bajo", 2),
                else_=3,
            )
            return (prioridad.asc(), Planta.created_at.desc())
        return (Planta.created_at.desc(),)

    @staticmethod
    def listar(
        owner_id: int,
        termino: str = "",
        page: int = 1,
        page_size: int = PAGE_SIZE,
        orden: str = "recientes",
        category: str | None = None,
        favorites: bool = False,
        names_only: bool = False,
        alternate_taxa: tuple[str, ...] = (),
    ) -> PaginaPlantas:
        page = max(1, page)
        texto = termino.strip()
        if orden not in PlantaService.ORDENES_VALIDOS:
            orden = "recientes"

        with session_scope() as session:
            query = select(Planta).where(Planta.owner_id == owner_id)
            count_query = select(func.count()).select_from(Planta).where(Planta.owner_id == owner_id)

            filters = []
            if texto:
                fields = [Planta.nombre_comun, Planta.nombre_cientifico]
                if not names_only:
                    fields.extend((Planta.familia, Planta.tipo))
                name_filters = [func.planet_normalize(field).contains(normalize(texto), autoescape=True)
                                for field in fields]
                if alternate_taxa:
                    name_filters.append(func.planet_normalize(Planta.nombre_cientifico).in_(alternate_taxa))
                filters.append(or_(*name_filters))
            if category:
                names = [name for name, facts in SPECIES.items() if category in facts]
                filters.append(func.planet_normalize(Planta.nombre_cientifico).in_(names))
                filters.append(Planta.confianza.in_(("alto", "medio")))
            if favorites:
                filters.append(Planta.encyclopedia_favorite.is_(True))
            query = query.where(*filters)
            count_query = count_query.where(*filters)

            total = session.scalar(count_query) or 0
            offset = (page - 1) * page_size
            items = list(
                session.scalars(
                    query.order_by(*PlantaService._clausula_orden(orden), Planta.id.desc())
                    .offset(offset)
                    .limit(page_size)
                )
            )
            return PaginaPlantas(
                items=items, total=total, page=page, page_size=page_size
            )

    @staticmethod
    def set_favorite(planta_id: int, owner_id: int, favorite: bool) -> bool:
        with session_scope() as session:
            result = session.execute(update(Planta).where(
                Planta.id == planta_id, Planta.owner_id == owner_id
            ).values(encyclopedia_favorite=favorite))
            return result.rowcount == 1

    @staticmethod
    def actualizar_notas(planta_id: int, notas: str, owner_id: int) -> Planta | None:
        with session_scope() as session:
            planta = session.scalar(select(Planta).where(Planta.id == planta_id, Planta.owner_id == owner_id))
            if planta is None:
                return None
            planta.notas_usuario = notas.strip()
            session.flush()
            session.refresh(planta)
            return planta

    @staticmethod
    def eliminar(planta_id: int, owner_id: int) -> bool:
        with session_scope() as session:
            planta = session.scalar(select(Planta).where(Planta.id == planta_id, Planta.owner_id == owner_id))
            if planta is None:
                return False
            image_path = UPLOADS_DIR / Path(planta.image_path).name
            session.delete(planta)
        try:
            image_path.unlink(missing_ok=True)
        except OSError:
            logging.getLogger(__name__).exception("Could not delete plant photo")
        return True

    @staticmethod
    def photo_for_owner(filename: str, owner_id: int) -> Path | None:
        with session_scope() as session:
            candidates = session.scalars(select(Planta.image_path).where(
                Planta.owner_id == owner_id,
                or_(Planta.image_path == filename, Planta.image_path.endswith("/" + filename, autoescape=True)),
            ))
            if any(Path(path).name == filename for path in candidates):
                return UPLOADS_DIR / filename
        return None

    @staticmethod
    def extension_desde_mime(mime_type: str) -> str:
        mapping = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
        }
        return mapping.get(mime_type, "jpg")
