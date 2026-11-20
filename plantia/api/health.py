"""Authenticated plant health endpoints shared by browser and API clients."""

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.responses import RedirectResponse, Response

from plantia import accounts
from plantia.config import ALLOWED_IMAGE_TYPES
from plantia.i18n import catalog, locale_for
from plantia.services import health
from plantia.services.gemini_service import GeminiService, GeminiUnavailable

router = APIRouter()


def _owner(request, plant_id):
    owner = request.state.account_id
    name = health.owner_record(plant_id, owner)
    if name is None:
        raise HTTPException(404, "Not found")
    return owner, name


def _save(plant_id, owner, kind, payload, photo=None, mime=None):
    try:
        event = health.save(plant_id, owner, kind, payload, photo, mime)
    except health.HistoryLimit:
        raise HTTPException(409, "health.limit") from None
    if event is None:
        raise HTTPException(404, "Not found")
    return event


async def _photo(file):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(400, "Choose a JPEG, PNG or WebP image")
    data = await file.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(413, "File or request too large")
    try:
        photo, mime = await run_in_threadpool(GeminiService.preparar_imagen, data, file.content_type)
    except (ValueError, OSError):
        raise HTTPException(400, "Could not process the image") from None
    if len(photo) > 2 * 1024 * 1024:
        raise HTTPException(413, "File or request too large")
    return photo, mime


@router.get("/plantas/{plant_id}/saude")
@router.get("/api/plantas/{plant_id}/saude")
def history(request: Request, plant_id: int, before: int | None = None):
    owner, name = _owner(request, plant_id)
    events = health.history(plant_id, owner, before)
    data = {"plant_id": plant_id, "name": name, "events": events,
            "next_before": events[-1]["id"] if len(events) == 20 else None}
    if request.url.path.startswith("/api/"):
        data["labels"] = {k: v for k, v in catalog(locale_for(request)).items() if k.startswith("health.")}
        return data
    from plantia.api.routes import templates
    return templates.TemplateResponse(request, "plant_health.html", data)


@router.post("/plantas/{plant_id}/saude/avaliar")
@router.post("/api/plantas/{plant_id}/saude/avaliar", status_code=201)
async def assess(request: Request, plant_id: int, photo: UploadFile = File(...),
                 leaf_change: bool = Form(False), spreading: bool = Form(False),
                 insects_seen: bool = Form(False), moisture: str = Form("unknown")):
    owner, _ = await run_in_threadpool(_owner, request, plant_id)
    try:
        context = health.Context(leaf_change=leaf_change, spreading=spreading, insects_seen=insects_seen, moisture=moisture)
    except ValidationError:
        raise HTTPException(422, "Invalid request") from None
    image, mime = await _photo(photo)
    if not await run_in_threadpool(accounts.allow_request, f"ai:health:{owner}", 10, 3600):
        raise HTTPException(429, "Too many requests")
    if not await run_in_threadpool(accounts.allow_request, "ai:global", 120, 3600):
        raise HTTPException(429, "Too many requests")
    try:
        result = await run_in_threadpool(health.analyze, image, mime, context)
    except GeminiUnavailable:
        raise HTTPException(503, "health.unavailable") from None
    payload = {**result.model_dump(mode="json"), "context": context.model_dump()}
    event = await run_in_threadpool(_save, plant_id, owner, "triage", payload, image, mime)
    if request.url.path.startswith("/api/"):
        return event
    return RedirectResponse(f"/plantas/{plant_id}/saude#event-{event['id']}", 303)


@router.post("/plantas/{plant_id}/saude/acompanhar")
@router.post("/api/plantas/{plant_id}/saude/acompanhar", status_code=201)
async def follow(request: Request, plant_id: int, trend: str = Form(...),
                 action: str = Form("observe"), note: str = Form(""), photo: UploadFile | None = File(None)):
    owner, _ = await run_in_threadpool(_owner, request, plant_id)
    try:
        update = health.FollowUp(trend=trend, action=action, note=note.strip())
    except ValidationError:
        raise HTTPException(422, "Invalid request") from None
    image, mime = await _photo(photo) if photo and photo.filename else (None, None)
    event = await run_in_threadpool(_save, plant_id, owner, "follow", update.model_dump(), image, mime)
    if request.url.path.startswith("/api/"):
        return event
    return RedirectResponse(f"/plantas/{plant_id}/saude#event-{event['id']}", 303)


@router.get("/api/plantas/{plant_id}/saude/fotos/{event_id}")
def photo(request: Request, plant_id: int, event_id: int):
    stored = health.photo_for(plant_id, event_id, request.state.account_id)
    if stored is None:
        raise HTTPException(404, "Not found")
    data, mime = stored
    return Response(data, media_type=mime)
