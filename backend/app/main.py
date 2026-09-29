import os
import secrets
from datetime import date, time
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select, text
from sqlalchemy.orm import Session

from .chatbot import build_matcher
from .database import Base, SessionLocal, engine, get_db
from .models import Appointment, Lead, Service

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(
    title="Mitalli Bridal World API",
    version="1.0.0",
    description="Deterministic spaCy Matcher chatbot and booking API.",
)

origins = os.getenv("ALLOWED_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if origins == "*" else [item.strip() for item in origins.split(",")],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)


class LeadCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    phone: str = Field(min_length=7, max_length=20)
    service_interest: str | None = Field(default=None, max_length=150)
    message: str | None = Field(default=None, max_length=1000)
    source: str = Field(default="website", max_length=50)


class AppointmentCreate(BaseModel):
    customer_name: str = Field(min_length=2, max_length=150)
    phone: str = Field(min_length=7, max_length=20)
    service_id: int | None = None
    appointment_date: date | None = None
    preferred_time: time | None = None
    message: str | None = Field(default=None, max_length=1000)


class AdminLogin(BaseModel):
    access_key: str = Field(min_length=1, max_length=300)


class AdminStatusUpdate(BaseModel):
    status: str = Field(pattern="^(pending|contacted|confirmed|completed|cancelled)$")


def require_admin(
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> bool:
    expected_key = os.getenv("ADMIN_ACCESS_KEY", "").strip()
    if not expected_key or not x_admin_key or not secrets.compare_digest(x_admin_key, expected_key):
        raise HTTPException(status_code=401, detail="Admin authentication required")
    return True


def _service_payload(service: Service) -> dict[str, Any]:
    return {
        "id": service.id,
        "category": service.category,
        "name": service.name,
        "description": service.description,
        "duration_minutes": service.duration_minutes,
        "price": service.price,
        "price_type": service.price_type,
    }


def _active_services(db: Session) -> list[dict[str, Any]]:
    services = db.scalars(
        select(Service).where(Service.is_active.is_(True)).order_by(Service.id)
    ).all()
    return [_service_payload(service) for service in services]


def _seed_services(db: Session) -> None:
    if db.scalar(select(Service.id).limit(1)) is not None:
        return
    seed = [
        ("Bridal Makeup", "Classic Bridal Makeup", "Personalized bridal makeup with a polished professional finish.", 180, 12000, "starting_from"),
        ("Bridal Makeup", "HD / Airbrush Bridal Makeup", "Camera-ready bridal finish for wedding celebrations and events.", 240, 18000, "starting_from"),
        ("Facial & Skincare", "Cleanup", "A refreshing cleanup for clean, comfortable skin.", 45, 500, "starting_from"),
        ("Facial & Skincare", "Fruit / Gold Facial", "Glow-focused facial options for special occasions.", 75, 1200, "starting_from"),
        ("Facial & Skincare", "Advanced Hydra Facial", "An advanced skincare service, subject to consultation.", 75, 3500, "starting_from"),
        ("Hair Care", "Hair Spa", "Nourishing hair care for a softer, healthier feel.", 75, 999, "starting_from"),
        ("Hair Care", "Smoothening / Keratin", "Smoothing and keratin services priced after hair consultation.", 180, 4500, "starting_from"),
        ("Hair Care", "Hair Styling", "Occasion-ready hair styling tailored to your look.", 60, None, "on_request"),
        ("Nails", "Manicure", "Clean, cared-for hands with a polished finish.", 45, None, "on_request"),
        ("Nails", "Pedicure", "Relaxing foot care with a neat, refreshed finish.", 60, None, "on_request"),
        ("Nails", "Nail Extensions", "Artificial nail extensions for a statement look.", 90, None, "on_request"),
        ("Hair Removal", "Waxing + Threading Package", "Convenient grooming for event-ready preparation.", 90, 800, "starting_from"),
        ("Styling", "Saree Draping", "Neat, secure saree draping for celebrations and bridal looks.", 45, None, "on_request"),
        ("Styling", "Event Makeup", "A polished makeup look for functions and celebrations.", 90, None, "on_request"),
    ]
    db.add_all(
        [
            Service(
                category=category,
                name=name,
                description=description,
                duration_minutes=duration,
                price=price,
                price_type=price_type,
            )
            for category, name, description, duration, price, price_type in seed
        ]
    )
    db.commit()


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        _seed_services(db)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok", "service": "mitalli-bridal-world"}


@app.get("/api/services")
def list_services(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return _active_services(db)


@app.post("/api/chat")
def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    services = _active_services(db)
    result = build_matcher(services).detect(payload.message)
    return {
        "intent": result.intent,
        "reply": result.reply,
        "service_id": result.service_id,
        "next_action": result.next_action,
    }


@app.post("/api/leads", status_code=201)
def create_lead(payload: LeadCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    lead = Lead(**payload.model_dump())
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return {"id": lead.id, "status": lead.status, "message": "Lead received"}


@app.post("/api/appointments", status_code=201)
def create_appointment(
    payload: AppointmentCreate, db: Session = Depends(get_db)
) -> dict[str, Any]:
    selected_service = db.get(Service, payload.service_id) if payload.service_id else None
    if payload.service_id is not None and selected_service is None:
        raise HTTPException(status_code=400, detail="Selected service is not available")
    appointment = Appointment(**payload.model_dump())
    lead = Lead(
        name=payload.customer_name,
        phone=payload.phone,
        source="website_booking",
        service_interest=selected_service.name if selected_service else None,
        message=payload.message,
    )
    db.add(appointment)
    db.add(lead)
    db.commit()
    db.refresh(appointment)
    return {
        "id": appointment.id,
        "status": appointment.status,
        "message": "Your appointment request has been received. Our team will confirm the slot.",
    }


@app.post("/api/admin/login")
def admin_login(payload: AdminLogin) -> dict[str, bool]:
    expected_key = os.getenv("ADMIN_ACCESS_KEY", "").strip()
    if not expected_key:
        raise HTTPException(status_code=503, detail="Admin access is not configured")
    if not secrets.compare_digest(payload.access_key, expected_key):
        raise HTTPException(status_code=401, detail="Invalid admin access key")
    return {"authenticated": True}


@app.get("/api/admin/summary")
def admin_summary(
    db: Session = Depends(get_db), _: bool = Depends(require_admin)
) -> dict[str, int]:
    counts = {
        status: db.scalar(
            select(func.count(Appointment.id)).where(Appointment.status == status)
        )
        or 0
        for status in ("pending", "contacted", "confirmed", "completed", "cancelled")
    }
    counts["total_appointments"] = sum(counts.values())
    counts["total_leads"] = db.scalar(select(func.count(Lead.id))) or 0
    return counts


@app.get("/api/admin/appointments")
def admin_appointments(
    db: Session = Depends(get_db), _: bool = Depends(require_admin)
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Appointment, Service.name)
        .outerjoin(Service, Appointment.service_id == Service.id)
        .order_by(desc(Appointment.created_at))
    ).all()
    return [
        {
            "id": appointment.id,
            "customer_name": appointment.customer_name,
            "phone": appointment.phone,
            "service": service_name or "Service not selected",
            "appointment_date": appointment.appointment_date.isoformat()
            if appointment.appointment_date
            else None,
            "preferred_time": appointment.preferred_time.strftime("%H:%M")
            if appointment.preferred_time
            else None,
            "message": appointment.message,
            "status": appointment.status,
            "created_at": appointment.created_at.isoformat()
            if appointment.created_at
            else None,
        }
        for appointment, service_name in rows
    ]


@app.patch("/api/admin/appointments/{appointment_id}")
def update_appointment_status(
    appointment_id: int,
    payload: AdminStatusUpdate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin),
) -> dict[str, Any]:
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    appointment.status = payload.status
    db.commit()
    return {"id": appointment.id, "status": appointment.status}


@app.get("/api/admin/leads")
def admin_leads(
    db: Session = Depends(get_db), _: bool = Depends(require_admin)
) -> list[dict[str, Any]]:
    leads = db.scalars(select(Lead).order_by(desc(Lead.created_at))).all()
    return [
        {
            "id": lead.id,
            "name": lead.name,
            "phone": lead.phone,
            "source": lead.source,
            "service_interest": lead.service_interest,
            "message": lead.message,
            "status": lead.status,
            "created_at": lead.created_at.isoformat() if lead.created_at else None,
        }
        for lead in leads
    ]


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")