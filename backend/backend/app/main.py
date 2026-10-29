"""Q-Transplant v4 FastAPI Application Entry Point."""
import logging
import os
import asyncio
from contextlib import asynccontextmanager
from sqlalchemy import inspect, text
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings, BASE_DIR
from app.database import Base, engine, SessionLocal
from app.routers import auth, donors, hospitals, matching, organizer, documents, groq_chat, fhir, recipients
from app.models import User, HospitalProfile, Donor
from app.security import get_password_hash
from app.services.autonomous_failover import check_and_execute_autonomous_failover

logger = logging.getLogger("qtransplant.startup")
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.normpath(os.path.join(_APP_DIR, "..", "public"))

# State capital coordinates (lat, lon) for seeded hospitals
_COORDS = {
    "Delhi NCR":  (28.6139, 77.2090),
    "Tamil Nadu": (13.0827, 80.2707),
}


def ensure_schema():
    """Create all tables and apply ALTER TABLE migrations for new columns."""
    Base.metadata.create_all(bind=engine)
    migrations = [
        "ALTER TABLE hospital_profiles ADD COLUMN doctor_phone VARCHAR",
        "ALTER TABLE hospital_profiles ADD COLUMN doctor_aadhaar_doc_url VARCHAR",
        "ALTER TABLE hospital_profiles ADD COLUMN latitude REAL",
        "ALTER TABLE hospital_profiles ADD COLUMN longitude REAL",
        "ALTER TABLE donors ADD COLUMN uploaded_at DATETIME",
        "ALTER TABLE donors ADD COLUMN is_allocated BOOLEAN DEFAULT 0",
        "ALTER TABLE donors ADD COLUMN allocated_to_hospital_id VARCHAR",
    ]
    with engine.connect() as conn:
        for stmt in migrations:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # Column already exists — ignore


def ensure_seed_data():
    """Bootstrap Root Organizer, sample hospitals, and donor datasets."""
    db = SessionLocal()
    try:
        # ── Root Organizer Accounts ──────────────────────────────────────────
        for root_email in [settings.ORGANIZER_BOOTSTRAP_EMAIL, "root@qtransplant.gov.in"]:
            u = db.query(User).filter(User.email == root_email).first()
            if not u:
                u = User(
                    email=root_email,
                    hashed_password=get_password_hash("root123456"),
                    role="ROOT", full_name="Root Network Organizer", status="active",
                )
                db.add(u)
            else:
                u.role = "ROOT"
                u.hashed_password = get_password_hash("root123456")
            db.commit()

        # ── Hospital 1: AIIMS Delhi ─────────────────────────────────────────
        hosp_1 = db.query(HospitalProfile).filter(
            HospitalProfile.registration_number == "GOV-HOSP-AIIMS-01"
        ).first()
        if not hosp_1:
            u1 = User(email="aiims@hospital.org", hashed_password=get_password_hash("hospital123"),
                      role="HOSPITAL", full_name="AIIMS Apex Medical Center", status="active")
            db.add(u1); db.flush()
            hosp_1 = HospitalProfile(
                user_id=u1.id, hospital_name="AIIMS Apex Medical Center",
                registration_number="GOV-HOSP-AIIMS-01", state="Delhi NCR",
                address="Ansari Nagar, New Delhi - 110029",
                contact_email="emergency@aiims.edu", reception_phone="+91-11-2658-8500",
                doctor_name="Dr. Rajesh Sharma, MD", doctor_phone="+91-11-2658-9999",
                doctor_aadhaar_masked="XXXX-XXXX-9812",
                doctor_aadhaar_doc_url="https://qtransplant.gov.in/docs/aiims_aadhaar.pdf",
                aadhaar_verified=True,
                gov_certificate_url="https://qtransplant.gov.in/certs/aiims.pdf",
                status="APPROVED",
                latitude=_COORDS["Delhi NCR"][0], longitude=_COORDS["Delhi NCR"][1],
            )
            db.add(hosp_1); db.flush()
            from datetime import datetime, timezone, timedelta
            t = datetime.now(timezone.utc)
            db.add_all([
                Donor(hospital_id=hosp_1.id, organ_type="Kidney", blood_group="O+", rh_factor="+",
                      hla_a="A2", hla_b="B7", hla_c="Cw7", hla_dr="DR4", hla_dq="DQ2",
                      age=32, health_status="Optimal", viability_hours_remaining=22.5, uploaded_at=t),
                Donor(hospital_id=hosp_1.id, organ_type="Liver", blood_group="A+", rh_factor="+",
                      hla_a="A1", hla_b="B8", hla_c="Cw3", hla_dr="DR3", hla_dq="DQ2",
                      age=28, health_status="Optimal", viability_hours_remaining=18.0, uploaded_at=t),
                Donor(hospital_id=hosp_1.id, organ_type="Heart", blood_group="O-", rh_factor="-",
                      hla_a="A3", hla_b="B27", hla_c="Cw1", hla_dr="DR1", hla_dq="DQ5",
                      age=24, health_status="Optimal", viability_hours_remaining=5.5, uploaded_at=t),
            ])

        # Update GIS coords if missing (for pre-existing seed hospitals)
        if hosp_1 and (hosp_1.latitude is None):
            hosp_1.latitude, hosp_1.longitude = _COORDS["Delhi NCR"]

        # ── Hospital 2: Apollo Chennai ──────────────────────────────────────
        hosp_2 = db.query(HospitalProfile).filter(
            HospitalProfile.registration_number == "GOV-HOSP-APOLLO-02"
        ).first()
        if not hosp_2:
            u2 = User(email="apollo@hospital.org", hashed_password=get_password_hash("hospital123"),
                      role="HOSPITAL", full_name="Apollo Multi-Specialty Hospital", status="active")
            db.add(u2); db.flush()
            hosp_2 = HospitalProfile(
                user_id=u2.id, hospital_name="Apollo Multi-Specialty Hospital",
                registration_number="GOV-HOSP-APOLLO-02", state="Tamil Nadu",
                address="Greams Lane, Off Greams Road, Chennai - 600006",
                contact_email="transplant@apollohospitals.com", reception_phone="+91-44-2829-0200",
                doctor_name="Dr. Ananya Reddy, MS", doctor_phone="+91-44-2829-9999",
                doctor_aadhaar_masked="XXXX-XXXX-4531",
                doctor_aadhaar_doc_url="https://qtransplant.gov.in/docs/apollo_aadhaar.pdf",
                aadhaar_verified=True,
                gov_certificate_url="https://qtransplant.gov.in/certs/apollo.pdf",
                status="APPROVED",
                latitude=_COORDS["Tamil Nadu"][0], longitude=_COORDS["Tamil Nadu"][1],
            )
            db.add(hosp_2); db.flush()
            from datetime import datetime, timezone
            t = datetime.now(timezone.utc)
            db.add_all([
                Donor(hospital_id=hosp_2.id, organ_type="Kidney", blood_group="B+", rh_factor="+",
                      hla_a="A11", hla_b="B35", hla_c="Cw4", hla_dr="DR15", hla_dq="DQ6",
                      age=41, health_status="Optimal", viability_hours_remaining=20.0, uploaded_at=t),
                Donor(hospital_id=hosp_2.id, organ_type="Pancreas", blood_group="O+", rh_factor="+",
                      hla_a="A2", hla_b="B44", hla_c="Cw5", hla_dr="DR7", hla_dq="DQ3",
                      age=29, health_status="Optimal", viability_hours_remaining=14.0, uploaded_at=t),
                Donor(hospital_id=hosp_2.id, organ_type="Lungs", blood_group="AB+", rh_factor="+",
                      hla_a="A24", hla_b="B51", hla_c="Cw15", hla_dr="DR4", hla_dq="DQ8",
                      age=30, health_status="Optimal", viability_hours_remaining=8.0, uploaded_at=t),
            ])

        if hosp_2 and (hosp_2.latitude is None):
            hosp_2.latitude, hosp_2.longitude = _COORDS["Tamil Nadu"]

        db.commit()
        logger.info("Seed data bootstrapped successfully.")
    except Exception as e:
        logger.exception("Error bootstrapping seed data: %s", e)
    finally:
        db.close()


def init_persistent_ledger():
    """Load audit ledger chain from SQLite on startup."""
    from app.audit_ledger import audit_ledger
    db = SessionLocal()
    try:
        audit_ledger.load_from_db(db)
        logger.info(f"Audit ledger loaded: {audit_ledger.total_blocks} blocks, valid={audit_ledger.is_chain_valid()}")
    finally:
        db.close()


async def failover_background_loop():
    """Background loop: check for expired urgent requests every 30 seconds."""
    while True:
        try:
            db = SessionLocal()
            check_and_execute_autonomous_failover(db)
            db.close()
        except Exception as e:
            logger.exception("Background failover error: %s", e)
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_schema()
    ensure_seed_data()
    init_persistent_ledger()
    asyncio.create_task(failover_background_loop())
    yield


app = FastAPI(
    title="Q-Transplant v4 API",
    description=(
        "Government-Grade Organ Matching & Inter-Hospital Emergency Network API. "
        "Clinical scoring: 6-locus HLA weighting, GIS Haversine viability decay, "
        "PRA sensitization gating, SHA-256 immutable audit ledger, HL7 FHIR R4 export."
    ),
    version="4.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ── Routers — all prefixes standardised ─────────────────────────────────────
# Routers that already carry their own /api/v1/... prefix (legacy kept as-is)
for r in (
    auth.router,
    organizer.router,   # /api/v1/organizer
    donors.router,      # /api/v1/donors
    matching.router,    # /api/v1/matching  ← NOTE: prefix inside router was removed; passed here
    groq_chat.router,
    documents.router,
    hospitals.router,
    fhir.router,        # /api/v1/fhir
):
    app.include_router(r)

# New v4 recipients router — prefix /api/v1 added here
app.include_router(recipients.router, prefix="/api/v1")


@app.get("/api", tags=["Health"])
def api_status():
    return {"service": "Q-Transplant v4 API", "status": "online", "version": "4.0.0",
            "features": ["6-locus HLA scoring", "GIS viability decay", "PRA gating",
                         "SHA-256 audit ledger", "HL7 FHIR R4", "Recipient waiting list"]}


@app.get("/health", tags=["Health"])
def health():
    from app.audit_ledger import audit_ledger
    return {"status": "ok", "database": "connected",
            "audit_chain_valid": audit_ledger.is_chain_valid(),
            "audit_blocks": audit_ledger.total_blocks}


# ── Static files ──────────────────────────────────────────────────────────────
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

if os.path.isdir(PUBLIC_DIR):
    app.mount("/", StaticFiles(directory=PUBLIC_DIR, html=True), name="frontend")
