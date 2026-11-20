"""Private encyclopedia views for identified plants."""

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, StrictBool

from plantia.i18n import translations
from plantia.services.botany import FILTERS, SPECIES, profile
from plantia.utils.taxon import normalize
from plantia.services.planta_service import PlantaService

router = APIRouter()


class FavoriteUpdate(BaseModel):
    favorite: StrictBool


def _results(request, q, category, favorite, page):
    if category and category not in FILTERS:
        raise HTTPException(400, "botany.invalid_category")
    translate = translations(request)["tr"]
    term = normalize(q)
    alternate_taxa = tuple(
        name for name, facts in SPECIES.items()
        if term and term in normalize(translate(facts["common_name"].message))
    )
    return PlantaService.listar(request.state.account_id, termino=q, page=page, category=category,
                               favorites=favorite, names_only=True, alternate_taxa=alternate_taxa)


def _profile(request, plant_id):
    plant = PlantaService.obtener_por_id(plant_id, request.state.account_id)
    if plant is None:
        raise HTTPException(404, "Not found")
    return profile(plant, translations(request)["tr"])


@router.get("/enciclopedia")
def encyclopedia(request: Request, q: str = Query("", max_length=150),
                 category: str = Query("", max_length=30), favorite: bool = False,
                 page: int = Query(1, ge=1, le=100_000)):
    from plantia.api.routes import templates
    results = _results(request, q, category, favorite, page)
    return templates.TemplateResponse(request, "encyclopedia.html", {
        "results": results, "q": q, "category": category, "favorite": favorite, "filters": FILTERS,
    })


@router.get("/enciclopedia/{plant_id}")
def encyclopedia_plant(request: Request, plant_id: int):
    from plantia.api.routes import templates
    return templates.TemplateResponse(request, "botany_profile.html", {"profile": _profile(request, plant_id)})


@router.post("/enciclopedia/{plant_id}/favorito")
def favorite_form(request: Request, plant_id: int, favorite: bool = Form(...)):
    if not PlantaService.set_favorite(plant_id, request.state.account_id, favorite):
        raise HTTPException(404, "Not found")
    return RedirectResponse(f"/enciclopedia/{plant_id}", 303)


@router.get("/api/enciclopedia")
def encyclopedia_api(request: Request, q: str = Query("", max_length=150),
                     category: str = Query("", max_length=30), favorite: bool = False,
                     page: int = Query(1, ge=1, le=100_000)):
    results = _results(request, q, category, favorite, page)
    translate = translations(request)["tr"]
    return {
        "total": results.total, "page": results.page, "total_pages": results.total_pages,
        "categories": [{"key": key, "label": translate(f"botany.field.{key}")} for key in FILTERS],
        "items": [{"id": plant.id, "common_name": plant.nombre_comun, "scientific_name": plant.nombre_cientifico,
                   "favorite": plant.encyclopedia_favorite} for plant in results.items],
    }


@router.get("/api/enciclopedia/{plant_id}")
def encyclopedia_plant_api(request: Request, plant_id: int):
    return _profile(request, plant_id)


@router.patch("/api/enciclopedia/{plant_id}/favorito")
def favorite_api(request: Request, plant_id: int, update: FavoriteUpdate):
    if not PlantaService.set_favorite(plant_id, request.state.account_id, update.favorite):
        raise HTTPException(404, "Not found")
    return {"favorite": update.favorite}
