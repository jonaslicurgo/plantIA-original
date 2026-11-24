"""Authenticated plant health endpoints shared by browser and API clients."""

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.responses import RedirectResponse, Response

from plantia import accounts
from plantia.config import ALLOWED_IMAGE_TYPES, get_gemini_model
from plantia.i18n import catalog, locale_for
from plantia.services import ai_meter, health, health_usage
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
        photo, mime = await run_in_threadpool(
            GeminiService.preparar_imagen, data, file.content_type, max_dimension=1440, jpeg_only=True, quality=84
        )
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
            "next_before": events[-1]["id"] if len(events) == 20 else None,
            "benefits": ai_meter.available_features(owner),
            "comparison": health.comparison(plant_id, owner), "usage": health_usage.totals(owner),
            "action_choices": [item.value for item in health.Action],
            "sources": [{"name": name, "url": url} for name, url in health.SOURCES]}
    if request.url.path.startswith("/api/"):
        data["labels"] = {k: v for k, v in catalog(locale_for(request)).items() if k.startswith("health.")}
        return data
    from plantia.api.routes import templates
    return templates.TemplateResponse(request, "plant_health.html", data)


@router.post("/plantas/{plant_id}/saude/avaliar")
@router.post("/api/plantas/{plant_id}/saude/avaliar", status_code=201)
async def assess(request: Request, plant_id: int, photo: UploadFile = File(...),
                 leaf_change: bool = Form(False), spreading: bool = Form(False),
                 insects_seen: bool = Form(False), moisture: str = Form("unknown"),
                 watering: str = Form("unknown"), lighting: str = Form("unknown"),
                 location: str = Form("unknown"), soil: str = Form("unknown"),
                 temperature: str = Form("unknown"), symptoms: str = Form("", max_length=300),
                 environment: str = Form("", max_length=300)):
    owner, _ = await run_in_threadpool(_owner, request, plant_id)
    await run_in_threadpool(ai_meter.check_access, owner, "diagnosis")
    try:
        context = health.Context(leaf_change=leaf_change, spreading=spreading, insects_seen=insects_seen,
                                 moisture=moisture, watering=watering, lighting=lighting, location=location,
                                 soil=soil, temperature=temperature, symptoms=symptoms.strip(), environment=environment.strip())
    except ValidationError:
        raise HTTPException(422, "Invalid request") from None
    image, mime = await _photo(photo)
    def diagnosis():
        result = health.analyze(image, mime, context)
        return {**result.model_dump(mode="json"), "context": context.model_dump()}

    event = await run_in_threadpool(
        _ai_run, plant_id, owner, "assess", "triage", context.model_dump(), diagnosis, image, mime
    )
    if request.url.path.startswith("/api/"):
        return event
    return RedirectResponse(f"/plantas/{plant_id}/saude#event-{event['id']}", 303)


@router.post("/plantas/{plant_id}/saude/acompanhar")
@router.post("/api/plantas/{plant_id}/saude/acompanhar", status_code=201)
async def follow(request: Request, plant_id: int, trend: str = Form(...),
                 action: str = Form("observe"), note: str = Form(""), photo: UploadFile | None = File(None),
                 confirmed_by_specialist: str = Form("", max_length=300)):
    owner, _ = await run_in_threadpool(_owner, request, plant_id)
    try:
        update = health.FollowUp(trend=trend, action=action, note=note.strip(), confirmed_by_specialist=confirmed_by_specialist.strip())
    except ValidationError:
        raise HTTPException(422, "Invalid request") from None
    image, mime = await _photo(photo) if photo and photo.filename else (None, None)
    event = await run_in_threadpool(_save, plant_id, owner, "follow", update.model_dump(), image, mime)
    if request.url.path.startswith("/api/"):
        return event
    return RedirectResponse(f"/plantas/{plant_id}/saude#event-{event['id']}", 303)


def _ai_run(plant_id, owner, operation, kind, context, compute, image=None, mime=None):
    try:
        key = health_usage.fingerprint(operation, get_gemini_model(), context, image or b"")
    except ValueError:
        raise HTTPException(503, "health.unavailable") from None
    try:
        usage, cached = health_usage.reserve(owner, plant_id, operation, key)
    except health_usage.Busy:
        raise HTTPException(409, "health.busy") from None
    except health_usage.Limit:
        raise HTTPException(429, "Too many requests") from None
    if cached is not None:
        return cached
    if usage is None:
        raise HTTPException(404, "Not found")
    if not accounts.allow_request("ai:global", 120, 3600):
        health_usage.finish(usage, "rejected")
        raise HTTPException(429, "Too many requests")
    try:
        with ai_meter.measure(owner, "diagnosis" if operation == "assess" else "assistant"):
            payload = compute()
        event = _save(plant_id, owner, kind, payload, image, mime)
    except HTTPException as exc:
        health_usage.finish(usage, "rejected" if exc.detail in {"commercial.disabled", "commercial.quota", "commercial.concurrent"} else "failed")
        raise
    except GeminiUnavailable:
        health_usage.finish(usage, "failed")
        raise HTTPException(503, "health.unavailable") from None
    except Exception:
        health_usage.finish(usage, "failed")
        raise
    health_usage.finish(usage, "success", event["id"])
    return event


@router.post("/plantas/{plant_id}/saude/assistente")
@router.post("/api/plantas/{plant_id}/saude/assistente", status_code=201)
def assistant(request: Request, plant_id: int, question: str = Form(..., max_length=400)):
    owner, _ = _owner(request, plant_id)
    ai_meter.check_access(owner, "assistant")
    question = question.strip()
    if not question:
        raise HTTPException(422, "Invalid request")
    assessments = health.latest_assessments(plant_id, owner)
    assessment = assessments[0]["data"] if assessments else None
    evidence = ({key: assessment[key] for key in ("status", "concern", "signs", "findings")}
                if assessment is not None else None)

    def reply():
        answer = health.assist(question, evidence)
        return {"question": question, **answer.model_dump(mode="json")}

    event = _ai_run(plant_id, owner, "assistant", "assistant", {"question": question, "evidence": evidence}, reply)
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
