"""
Rutas FastAPI: páginas HTML y API REST.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from threading import Lock

from starlette.concurrency import run_in_threadpool

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from plantia import accounts
from plantia.api.auth import router as auth_router
from plantia.api.health import router as health_router
from plantia.api.encyclopedia import router as encyclopedia_router
from plantia.config import ALLOWED_IMAGE_TYPES, MAX_IMAGE_SIZE_BYTES, PAGE_SIZE, UPLOADS_DIR, ensure_directories, get_gemini_model
from plantia.i18n import LANGUAGES, catalog, locale_for, translations
from plantia.security import enforce_security, secure_cookie
from plantia.database import init_database
from plantia.schemas.planta import PlantaListResponse, PlantaResponse, PlantaUpdate
from plantia.utils.taxon import species_name
from plantia.services.gemini_service import GeminiService, GeminiUnavailable, PROMPT
from plantia.services.planta_service import PlantaService
from plantia.utils.jinja_filters import detalle_json_fields

PACKAGE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR), context_processors=[translations])
templates.env.globals["image_url"] = lambda path: f"/uploads/{Path(path).name}"


def _contexto_detalle(planta, *, mensaje: str | None, focus_cuaderno: bool, luna) -> dict:
    return {
        "planta": planta,
        "mensaje": mensaje,
        "focus_cuaderno": focus_cuaderno,
        "luna": luna,
        **detalle_json_fields(planta),
    }


def _planta_to_response(planta) -> PlantaResponse:
    response = PlantaResponse.model_validate(planta)
    return response.model_copy(update={"image_path": Path(planta.image_path).name, "toxicidad_perros": "", "toxicidad_gatos": ""})


def _pagina_lista(pagina, q: str) -> PlantaListResponse:
    return PlantaListResponse(
        items=[_planta_to_response(p) for p in pagina.items],
        total=pagina.total,
        page=pagina.page,
        page_size=pagina.page_size,
        total_pages=pagina.total_pages,
    )


async def _leer_imagen(file: UploadFile) -> tuple[bytes, str]:
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(400, "Choose a JPEG, PNG or WebP image")
    content = await file.read(MAX_IMAGE_SIZE_BYTES + 1)
    if len(content) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(413, "File or request too large")
    if not content:
        raise HTTPException(400, "The image is empty")
    return content, file.content_type


_IDENTIFICATION_LOCKS = tuple(Lock() for _ in range(32))


def _identify(content, mime_type, owner, locale):
    prepared, actual_type = GeminiService.preparar_imagen(content, mime_type)
    try:
        model = get_gemini_model()
    except ValueError as exc:
        raise GeminiUnavailable("Invalid server model configuration") from exc
    context = f"{owner}\0{locale}\0{model}\0{actual_type}\0{PROMPT}\0"
    cache_key = hashlib.sha256(context.encode() + prepared).hexdigest()
    with _IDENTIFICATION_LOCKS[int(cache_key[:8], 16) % len(_IDENTIFICATION_LOCKS)]:
        cached = PlantaService.find_cached_identification(owner, cache_key)
        if cached and (UPLOADS_DIR / Path(cached.image_path).name).is_file():
            return cached
        result = GeminiService.identificar(prepared, actual_type, LANGUAGES[locale][1], already_prepared=True)
        if (result.estado_identificacion == "inconclusive" or result.confianza == "bajo"
                or not result.nombre_comun.strip() or not species_name(result.nombre_cientifico)):
            raise HTTPException(422, "botany.inconclusive")
        path = PlantaService.guardar_imagen(prepared, PlantaService.extension_desde_mime(actual_type))
        try:
            return PlantaService.crear_desde_identificacion(result, path, owner, cache_key)
        except Exception:
            Path(path).unlink(missing_ok=True)
            raise


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/idioma")
def set_language(request: Request, language: str = Form(...), page: str = Form("/")):
    if language not in LANGUAGES:
        raise HTTPException(400, "Invalid language")
    allowed = {"/", "/plantas", "/enciclopedia", "/conta/entrar", "/conta/cadastro", "/conta/recuperar", "/conta/redefinir"}
    response = RedirectResponse(page if page in allowed or re.fullmatch(r"/(?:(?:plantas|enciclopedia)/[0-9]+|plantas/[0-9]+/saude)", page) else "/", 303)
    response.set_cookie("planet_language", language, max_age=31536000, httponly=True,
                        secure=secure_cookie(), samesite="lax")
    return response


@router.get("/uploads/{filename}")
def private_upload(request: Request, filename: str):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}\.(jpg|jpeg|png|webp)", filename):
        raise HTTPException(404, "Not found")
    path = PlantaService.photo_for_owner(filename, request.state.account_id)
    if path is None or not path.is_file() or path.is_symlink():
        raise HTTPException(404, "Not found")
    return FileResponse(path)


# --- Páginas HTML ---


@router.get("/", response_class=HTMLResponse)
async def pagina_inicio(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"planta": None, "error": None, "mensaje": None, "focus_cuaderno": False},
    )


@router.post("/identificar", response_class=HTMLResponse)
async def identificar_planta(request: Request, file: UploadFile = File(...)):
    try:
        content, mime_type = await _leer_imagen(file)
        planta = await run_in_threadpool(_identify, content, mime_type, request.state.account_id, locale_for(request))
        return templates.TemplateResponse(
            request, "index.html", {"planta": planta, "focus_cuaderno": True}
        )
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(400, "Could not identify this image") from None
    except GeminiUnavailable:
        raise HTTPException(503, "Plant identification is temporarily unavailable") from None
    except Exception:
        logging.getLogger(__name__).error("Plant identification failed")
        raise HTTPException(500, "Could not process the image") from None


@router.get("/plantas", response_class=HTMLResponse)
def pagina_historial(
    request: Request,
    q: str = Query("", alias="q"),
    page: int = Query(1, ge=1),
    orden: str = Query("recientes", alias="orden"),
    mensaje: str = Query("", alias="mensaje"),
):
    pagina = PlantaService.listar(request.state.account_id, termino=q, page=page, orden=orden)
    if orden not in PlantaService.ORDENES_VALIDOS:
        orden = "recientes"
    return templates.TemplateResponse(
        request,
        "historial.html",
        {
            "plantas": pagina.items,
            "q": q,
            "orden": orden,
            "page": pagina.page,
            "total": pagina.total,
            "total_pages": pagina.total_pages,
            "page_size": pagina.page_size,
            "mensaje": "Plant deleted" if mensaje == "Plant deleted" else None,
        },
    )


@router.get("/plantas/{planta_id}", response_class=HTMLResponse)
def pagina_detalle(request: Request, planta_id: int):
    from plantia.utils.moon import moon_info

    planta = PlantaService.obtener_por_id(planta_id, request.state.account_id)
    if planta is None:
        raise HTTPException(status_code=404, detail="Not found")
    return templates.TemplateResponse(
        request,
        "detalle.html",
        _contexto_detalle(
            planta,
            mensaje=None,
            focus_cuaderno=False,
            luna=moon_info(),
        ),
    )


@router.post("/plantas/{planta_id}/notas", response_class=HTMLResponse)
def guardar_notas(
    request: Request,
    planta_id: int,
    notas_usuario: str = Form(""),
    redirect: str = Form("detalle"),
):
    from plantia.utils.moon import moon_info

    planta = PlantaService.actualizar_notas(planta_id, notas_usuario, request.state.account_id)
    if planta is None:
        raise HTTPException(status_code=404, detail="Not found")
    mensaje = "Note saved"
    contexto = {
        "planta": planta,
        "mensaje": mensaje,
        "focus_cuaderno": True,
    }
    if redirect == "index":
        return templates.TemplateResponse(
            request,
            "index.html",
            {**contexto, "error": None},
        )
    return templates.TemplateResponse(
        request,
        "detalle.html",
        _contexto_detalle(
            planta,
            mensaje=mensaje,
            focus_cuaderno=True,
            luna=moon_info(),
        ),
    )


@router.post("/plantas/{planta_id}/eliminar")
def eliminar_planta(request: Request, planta_id: int):
    if not PlantaService.eliminar(planta_id, request.state.account_id):
        raise HTTPException(status_code=404, detail="Not found")
    return RedirectResponse(
        url="/plantas?mensaje=Plant+deleted",
        status_code=303,
    )


# --- API REST ---


@router.post("/api/plantas/identificar", response_model=PlantaResponse)
async def api_identificar(request: Request, file: UploadFile = File(...)):
    try:
        content, mime_type = await _leer_imagen(file)
        planta = await run_in_threadpool(_identify, content, mime_type, request.state.account_id, locale_for(request))
        return _planta_to_response(planta)
    except ValueError:
        raise HTTPException(400, "Could not identify this image") from None
    except GeminiUnavailable:
        raise HTTPException(503, "Plant identification is temporarily unavailable") from None
    except HTTPException:
        raise
    except Exception:
        logging.getLogger(__name__).error("Plant identification failed")
        raise HTTPException(500, "Could not process the image") from None


@router.get("/api/plantas", response_model=PlantaListResponse)
def api_listar(
    request: Request,
    q: str = Query("", alias="q"),
    page: int = Query(1, ge=1),
    page_size: int = Query(PAGE_SIZE, ge=1, le=100),
    orden: str = Query("recientes", alias="orden"),
):
    pagina = PlantaService.listar(request.state.account_id, termino=q, page=page, page_size=page_size, orden=orden)
    return _pagina_lista(pagina, q)


@router.get("/api/plantas/{planta_id}", response_model=PlantaResponse)
def api_detalle(request: Request, planta_id: int):
    planta = PlantaService.obtener_por_id(planta_id, request.state.account_id)
    if planta is None:
        raise HTTPException(status_code=404, detail="Not found")
    return _planta_to_response(planta)


@router.patch("/api/plantas/{planta_id}", response_model=PlantaResponse)
def api_actualizar(request: Request, planta_id: int, datos: PlantaUpdate):
    if datos.notas_usuario is None:
        raise HTTPException(status_code=400, detail="No changes provided")
    planta = PlantaService.actualizar_notas(planta_id, datos.notas_usuario, request.state.account_id)
    if planta is None:
        raise HTTPException(status_code=404, detail="Not found")
    return _planta_to_response(planta)


@router.post("/api/plantas/{planta_id}/notas", response_model=PlantaResponse)
def api_guardar_notas(request: Request, planta_id: int, datos: PlantaUpdate):
    """Guardar notas del cuaderno (alternativa POST para clientes móviles)."""
    if datos.notas_usuario is None:
        raise HTTPException(status_code=400, detail="No changes provided")
    planta = PlantaService.actualizar_notas(planta_id, datos.notas_usuario, request.state.account_id)
    if planta is None:
        raise HTTPException(status_code=404, detail="Not found")
    return _planta_to_response(planta)


@router.delete("/api/plantas/{planta_id}", status_code=204)
def api_eliminar(request: Request, planta_id: int):
    if not PlantaService.eliminar(planta_id, request.state.account_id):
        raise HTTPException(status_code=404, detail="Not found")


def create_app():
    """Crea y configura la aplicación FastAPI."""
    from fastapi import FastAPI

    ensure_directories()
    init_database()

    accounts.initialize_accounts()
    app = FastAPI(
        docs_url=None, redoc_url=None, openapi_url=None,
        title="PLANET-IA",
        description="Identificación de plantas con Gemini",
        version="0.1.0",
    )
    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException

    async def error_handler(request, exc):
        status = exc.status_code if isinstance(exc, StarletteHTTPException) else 422
        key = exc.detail if isinstance(exc, StarletteHTTPException) and isinstance(exc.detail, str) else "Invalid request"
        if request.url.path.startswith(("/api/", "/uploads/")):
            body = {"detail": catalog(locale_for(request)).get(key, key)}
            if key == "botany.inconclusive":
                body["code"] = "identification_inconclusive"
            return JSONResponse(body, status)
        return templates.TemplateResponse(request, "error.html", {"message_key": key}, status_code=status)

    app.add_exception_handler(StarletteHTTPException, error_handler)
    app.add_exception_handler(RequestValidationError, error_handler)
    app.middleware("http")(enforce_security)
    app.include_router(auth_router)
    app.include_router(health_router)
    app.include_router(encyclopedia_router)
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app
