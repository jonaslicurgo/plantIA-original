"""Private garden profiles and shared care agenda for existing plant records."""

from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, Form, HTTPException, Query, Request
from sqlalchemy import func, select, update
from starlette.responses import RedirectResponse

from plantia.database import session_scope
from plantia.models import GardenProfile, GardenTask, Planta
from plantia.utils.taxon import normalize

router = APIRouter()
CARE_TYPES = ("water", "fertilize", "prune", "repot", "review")
CareType = Literal["water", "fertilize", "prune", "repot", "review"]


def _owned(owner):
    return Planta.owner_id == owner


def _plant(db, plant_id, owner):
    plant = db.scalar(select(Planta).where(Planta.id == plant_id, _owned(owner)))
    if plant is None:
        raise HTTPException(404, "Not found")
    return plant


def _plant_card(plant, profile):
    return {"id": plant.id, "name": plant.nombre_comun, "scientific_name": plant.nombre_cientifico,
            "nickname": profile.nickname if profile else "", "location": profile.location if profile else ""}


def _task_row(task, plant):
    return {"id": task.id, "plant_id": plant.id, "name": plant.nombre_comun, "kind": task.kind,
            "due_on": task.due_on.isoformat(), "completed": task.completed_at is not None}


def _is_api(request):
    return request.url.path.startswith("/api/")


def _view(request, template, data):
    if _is_api(request):
        return data
    from plantia.api.routes import templates
    return templates.TemplateResponse(request, template, data)


@router.get("/jardim")
@router.get("/api/jardim")
def garden(request: Request, location: str = Query("", max_length=80),
           page: int = Query(1, ge=1, le=100_000), done: bool = False,
           agenda_page: int = Query(1, ge=1, le=100_000)):
    owner = request.state.account_id
    with session_scope() as db:
        plants = select(Planta, GardenProfile).outerjoin(GardenProfile).where(_owned(owner))
        agenda = select(GardenTask, Planta).join(Planta).outerjoin(GardenProfile).where(
            _owned(owner), GardenTask.completed_at.is_not(None) if done else GardenTask.completed_at.is_(None)
        )
        if location:
            condition = func.planet_normalize(GardenProfile.location) == normalize(location)
            plants = plants.where(condition)
            agenda = agenda.where(condition)
        locations = db.scalars(select(GardenProfile.location).join(Planta).where(
            _owned(owner), GardenProfile.location != ""
        ).distinct().order_by(GardenProfile.location)).all()
        plant_rows = list(db.execute(plants.order_by(Planta.id.desc()).offset((page - 1) * 24).limit(25)))
        task_rows = list(db.execute(agenda.order_by(GardenTask.due_on, GardenTask.id).offset((agenda_page - 1) * 24).limit(25)))
        data = {"plants": [_plant_card(*row) for row in plant_rows[:24]],
                "tasks": [_task_row(*row) for row in task_rows[:24]], "locations": locations,
                "location": location, "page": page, "more": len(plant_rows) > 24,
                "done": done, "agenda_page": agenda_page, "agenda_more": len(task_rows) > 24}
    return _view(request, "garden.html", data)


@router.get("/jardim/{plant_id}")
@router.get("/api/jardim/{plant_id}")
def specimen(request: Request, plant_id: int, page: int = Query(1, ge=1, le=100_000),
             kind: CareType = "water", due_on: date | None = None):
    with session_scope() as db:
        plant = _plant(db, plant_id, request.state.account_id)
        profile = db.get(GardenProfile, plant_id)
        tasks = list(db.scalars(select(GardenTask).where(GardenTask.plant_id == plant_id)
            .order_by(GardenTask.completed_at.is_not(None), GardenTask.due_on, GardenTask.id)
            .offset((page - 1) * 24).limit(25)))
        data = {"plant": _plant_card(plant, profile), "tasks": [_task_row(task, plant) for task in tasks[:24]],
                "kinds": CARE_TYPES, "page": page, "more": len(tasks) > 24,
                "selected_kind": kind, "suggested_date": due_on.isoformat() if due_on else ""}
    return _view(request, "garden_plant.html", data)


@router.post("/jardim/{plant_id}/perfil")
@router.post("/api/jardim/{plant_id}/perfil")
def edit_profile(request: Request, plant_id: int, nickname: str = Form("", max_length=80),
                 location: str = Form("", max_length=80)):
    with session_scope() as db:
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        plant = _plant(db, plant_id, request.state.account_id)
        profile = db.get(GardenProfile, plant_id)
        if profile is None:
            profile = GardenProfile(plant_id=plant.id)
            db.add(profile)
        profile.nickname = " ".join(nickname.split())
        profile.location = " ".join(location.split())
        data = _plant_card(plant, profile)
    return data if _is_api(request) else RedirectResponse(f"/jardim/{plant_id}", 303)


@router.post("/jardim/{plant_id}/tarefas")
@router.post("/api/jardim/{plant_id}/tarefas", status_code=201)
def add_task(request: Request, plant_id: int, kind: CareType = Form(...), due_on: date = Form(...)):
    with session_scope() as db:
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        plant = _plant(db, plant_id, request.state.account_id)
        existing = db.scalar(select(GardenTask).where(GardenTask.plant_id == plant_id, GardenTask.kind == kind,
            GardenTask.due_on == due_on, GardenTask.completed_at.is_(None)).limit(1))
        if existing is None:
            count = db.scalar(select(func.count(GardenTask.id)).join(Planta).where(_owned(request.state.account_id)))
            if count >= 2000:
                raise HTTPException(409, "garden.limit")
            existing = GardenTask(plant_id=plant_id, kind=kind, due_on=due_on)
            db.add(existing)
            db.flush()
        data = _task_row(existing, plant)
    return data if _is_api(request) else RedirectResponse(f"/jardim/{plant_id}", 303)


@router.post("/jardim/{plant_id}/tarefas/{task_id}/concluir")
@router.post("/api/jardim/{plant_id}/tarefas/{task_id}/concluir")
def complete(request: Request, plant_id: int, task_id: int):
    with session_scope() as db:
        owner = request.state.account_id
        query = select(GardenTask).join(Planta).where(
            GardenTask.id == task_id, GardenTask.plant_id == plant_id, _owned(owner))
        task = db.scalar(query)
        if task is None:
            raise HTTPException(404, "Not found")
        db.execute(update(GardenTask).where(
            GardenTask.id == task_id, GardenTask.plant_id == plant_id,
            GardenTask.plant_id.in_(select(Planta.id).where(_owned(owner))),
            GardenTask.completed_at.is_(None),
        ).values(completed_at=datetime.now(timezone.utc)))
    return {"completed": True} if _is_api(request) else RedirectResponse(f"/jardim/{plant_id}", 303)


@router.post("/jardim/{plant_id}/tarefas/{task_id}/reagendar")
@router.post("/api/jardim/{plant_id}/tarefas/{task_id}/reagendar")
def reschedule(request: Request, plant_id: int, task_id: int, due_on: date = Form(...)):
    with session_scope() as db:
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        plant = _plant(db, plant_id, request.state.account_id)
        task = db.scalar(select(GardenTask).where(GardenTask.id == task_id, GardenTask.plant_id == plant.id,
                                                  GardenTask.completed_at.is_(None)))
        if task is None:
            raise HTTPException(404, "Not found")
        duplicate = db.scalar(select(GardenTask.id).where(
            GardenTask.plant_id == plant.id, GardenTask.kind == task.kind, GardenTask.due_on == due_on,
            GardenTask.id != task.id, GardenTask.completed_at.is_(None),
        ).limit(1))
        if duplicate is not None:
            raise HTTPException(409, "garden.duplicate")
        task.due_on = due_on
        data = _task_row(task, plant)
    return data if _is_api(request) else RedirectResponse(f"/jardim/{plant_id}", 303)
