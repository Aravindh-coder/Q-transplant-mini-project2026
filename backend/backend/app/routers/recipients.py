"""Q-Transplant v4 — Recipient Waiting List Router.

Hospitals register patients on the national waiting list.
Each recipient can have a dedicated match run using the full clinical engine.
"""
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, HospitalProfile, Donor, Recipient, AuditLog
from app.security import require_role
from app.services.efficiency_engine import calculate_match_efficiency
from app.services.gis_engine import compute_gis_adjusted_viability

router = APIRouter(prefix="/recipients", tags=["Recipient Waiting List"])


# ─── Pydantic schemas ────────────────────────────────────────────────────────

class RecipientRegisterIn(BaseModel):
    patient_code: str = Field(..., description="Anonymous patient code e.g. PAT-AIIMS-007")
    organ_needed: str
    blood_group: str
    rh_factor: Optional[str] = "+"
    hla_a: Optional[str] = None
    hla_b: Optional[str] = None
    hla_c: Optional[str] = None
    hla_dr: Optional[str] = None
    hla_dq: Optional[str] = None
    pra_percentage: Optional[float] = Field(default=0.0, ge=0, le=100,
        description="Panel Reactive Antibody % (0-100). >70% = high crossmatch risk.")
    urgency_level: Optional[str] = "HIGH"
    additional_notes: Optional[str] = None


class RecipientStatusUpdate(BaseModel):
    status: str  # WAITING, MATCHED, TRANSPLANTED


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/register", summary="Register a patient on the organ waiting list")
def register_recipient(
    body: RecipientRegisterIn,
    user: User = Depends(require_role("HOSPITAL", "ROOT")),
    db: Session = Depends(get_db),
):
    hospital = db.query(HospitalProfile).filter(HospitalProfile.user_id == user.id).first()
    if user.role == "HOSPITAL" and (not hospital or hospital.status != "APPROVED"):
        raise HTTPException(403, "Hospital must be APPROVED to register recipients.")

    # For ROOT, use the first hospital as owner placeholder (or allow null)
    hospital_id = hospital.id if hospital else None
    if not hospital_id:
        raise HTTPException(400, "No hospital profile linked to this account.")

    # Prevent duplicate patient_code per hospital
    existing = db.query(Recipient).filter(
        Recipient.hospital_id == hospital_id,
        Recipient.patient_code == body.patient_code,
        Recipient.status == "WAITING",
    ).first()
    if existing:
        raise HTTPException(409, f"Patient code '{body.patient_code}' already on waiting list.")

    recipient = Recipient(
        hospital_id=hospital_id,
        patient_code=body.patient_code,
        organ_needed=body.organ_needed.strip().capitalize(),
        blood_group=body.blood_group.strip().upper(),
        rh_factor=body.rh_factor or "+",
        hla_a=body.hla_a,
        hla_b=body.hla_b,
        hla_c=body.hla_c,
        hla_dr=body.hla_dr,
        hla_dq=body.hla_dq,
        pra_percentage=body.pra_percentage or 0.0,
        urgency_level=(body.urgency_level or "HIGH").upper(),
        additional_notes=body.additional_notes,
        status="WAITING",
    )
    db.add(recipient)

    audit = AuditLog(
        user_id=user.id,
        action="RECIPIENT_REGISTERED",
        target=body.patient_code,
        meta={"organ": body.organ_needed, "urgency": body.urgency_level,
              "pra": body.pra_percentage, "hospital_id": hospital_id},
    )
    db.add(audit)
    db.commit()
    db.refresh(recipient)

    return {
        "status": "REGISTERED",
        "recipient_id": recipient.id,
        "patient_code": recipient.patient_code,
        "organ_needed": recipient.organ_needed,
        "urgency_level": recipient.urgency_level,
        "pra_percentage": recipient.pra_percentage,
        "message": f"Patient '{body.patient_code}' successfully added to the national waiting list.",
    }


@router.get("/waiting-list", summary="Get hospital's own recipient waiting list")
def get_waiting_list(
    user: User = Depends(require_role("HOSPITAL", "ROOT")),
    db: Session = Depends(get_db),
):
    hospital = db.query(HospitalProfile).filter(HospitalProfile.user_id == user.id).first()
    if user.role == "HOSPITAL" and not hospital:
        return []

    query = db.query(Recipient)
    if user.role == "HOSPITAL":
        query = query.filter(Recipient.hospital_id == hospital.id)

    recipients = query.order_by(Recipient.registered_at.desc()).all()
    return [_format_recipient(r) for r in recipients]


@router.get("/national-queue", summary="Root-only: all recipients across all hospitals")
def get_national_queue(
    organ_filter: Optional[str] = None,
    urgency_filter: Optional[str] = None,
    user: User = Depends(require_role("ROOT")),
    db: Session = Depends(get_db),
):
    query = db.query(Recipient).filter(Recipient.status == "WAITING")
    if organ_filter:
        query = query.filter(Recipient.organ_needed == organ_filter.strip().capitalize())
    if urgency_filter:
        query = query.filter(Recipient.urgency_level == urgency_filter.upper())
    recipients = query.order_by(Recipient.urgency_level, Recipient.registered_at).all()

    result = []
    for r in recipients:
        hosp = db.query(HospitalProfile).filter(HospitalProfile.id == r.hospital_id).first()
        d = _format_recipient(r)
        d["hospital_name"] = hosp.hospital_name if hosp else "Unknown"
        d["hospital_state"] = hosp.state if hosp else "Unknown"
        result.append(d)
    return result


@router.get("/{recipient_id}/match", summary="Run clinical match engine for a specific recipient")
def match_for_recipient(
    recipient_id: str,
    user: User = Depends(require_role("HOSPITAL", "ROOT")),
    db: Session = Depends(get_db),
):
    recipient = db.query(Recipient).filter(Recipient.id == recipient_id).first()
    if not recipient:
        raise HTTPException(404, "Recipient not found.")

    # Authorization: hospitals can only match their own recipients
    if user.role == "HOSPITAL":
        hospital = db.query(HospitalProfile).filter(HospitalProfile.user_id == user.id).first()
        if not hospital or recipient.hospital_id != hospital.id:
            raise HTTPException(403, "Cannot access another hospital's recipient records.")
    else:
        hospital = db.query(HospitalProfile).filter(HospitalProfile.id == recipient.hospital_id).first()

    recipient_spec = {
        "organ_type": recipient.organ_needed,
        "blood_group": recipient.blood_group,
        "hla_a": recipient.hla_a,
        "hla_b": recipient.hla_b,
        "hla_c": recipient.hla_c,
        "hla_dr": recipient.hla_dr,
        "hla_dq": recipient.hla_dq,
    }

    results = []
    donors = db.query(Donor).filter(Donor.is_allocated == False).all()

    for donor in donors:
        # Real-time viability decay from upload time
        now = datetime.now(timezone.utc)
        uploaded = donor.uploaded_at or donor.created_at
        if uploaded and uploaded.tzinfo is None:
            uploaded = uploaded.replace(tzinfo=timezone.utc)
        elapsed_hrs = (now - uploaded).total_seconds() / 3600.0 if uploaded else 0
        actual_viability = max(0.0, donor.viability_hours_remaining - elapsed_hrs)

        if actual_viability <= 0:
            continue  # Skip expired organs

        # GIS distance between donor hospital and recipient hospital
        donor_hosp = db.query(HospitalProfile).filter(HospitalProfile.id == donor.hospital_id).first()
        if not donor_hosp:
            continue

        # Skip self — can't transplant from same hospital's own donor to their patient
        # (allowed in real life but flag it)
        is_same_hospital = (donor_hosp.id == recipient.hospital_id)

        gis = compute_gis_adjusted_viability(
            stored_viability_hours=actual_viability,
            donor_lat=donor_hosp.latitude, donor_lon=donor_hosp.longitude,
            recipient_lat=hospital.latitude if hospital else None,
            recipient_lon=hospital.longitude if hospital else None,
            organ_type=donor.organ_needed if hasattr(donor, "organ_needed") else donor.organ_type,
            donor_state=donor_hosp.state,
            recipient_state=hospital.state if hospital else "",
        )

        if not gis["is_viable"]:
            continue  # Organ won't survive transport

        donor_spec = {
            "organ_type": donor.organ_type,
            "blood_group": donor.blood_group,
            "hla_a": donor.hla_a,
            "hla_b": donor.hla_b,
            "hla_c": donor.hla_c,
            "hla_dr": donor.hla_dr,
            "hla_dq": donor.hla_dq,
            "viability_hours_remaining": actual_viability,
            "health_status": donor.health_status,
        }

        metrics = calculate_match_efficiency(
            donor=donor_spec,
            recipient=recipient_spec,
            gis_data=gis,
            waiting_registered_at=recipient.registered_at,
            urgency_level=recipient.urgency_level,
            pra_percentage=recipient.pra_percentage,
        )

        if metrics.get("efficiency_score", 0) <= 0 or not metrics.get("is_compatible"):
            continue

        results.append({
            "donor_ref": f"DONOR-{donor.id[:8].upper()}",
            "donor_id": donor.id,
            "organ_type": donor.organ_type,
            "donor_blood_group": donor.blood_group,
            "efficiency_score_percentage": metrics["efficiency_score"],
            "score_breakdown": {
                "blood": metrics["blood_score"],
                "hla": metrics["hla_score"],
                "hla_pct": metrics["hla_percentage"],
                "viability": metrics["viability_score"],
                "waiting_time": metrics["wait_score"],
                "urgency": metrics["urgency_score"],
                "pra_penalty": metrics["pra_penalty"],
            },
            "gis_info": {
                "distance_km": metrics.get("distance_km"),
                "transport_hours": metrics.get("transport_hours"),
                "adjusted_viability_hours": metrics.get("adjusted_viability_hours"),
                "gis_available": metrics.get("gis_available"),
            },
            "pra_risk": metrics["pra_risk"],
            "pra_flag": metrics["pra_flag"],
            "pra_message": metrics["pra_message"],
            "is_same_hospital": is_same_hospital,
            "holding_hospital": {
                "hospital_id": donor_hosp.id,
                "hospital_name": donor_hosp.hospital_name,
                "state": donor_hosp.state,
                "address": donor_hosp.address,
                "reception_phone": donor_hosp.reception_phone,
                "contact_email": donor_hosp.contact_email,
                "authorized_doctor": donor_hosp.doctor_name,
            },
        })

    results.sort(key=lambda x: x["efficiency_score_percentage"], reverse=True)

    # Log to audit ledger
    from app.audit_ledger import audit_ledger
    audit_ledger.add_block(
        action="RECIPIENT_MATCH_SEARCH",
        details={
            "recipient_id": recipient_id,
            "patient_code": recipient.patient_code,
            "organ_needed": recipient.organ_needed,
            "matches_found": len(results),
        },
    )

    return {
        "recipient": _format_recipient(recipient),
        "total_matches": len(results),
        "matches": results,
    }


@router.post("/{recipient_id}/status", summary="Update recipient status (MATCHED / TRANSPLANTED)")
def update_recipient_status(
    recipient_id: str,
    body: RecipientStatusUpdate,
    user: User = Depends(require_role("HOSPITAL", "ROOT")),
    db: Session = Depends(get_db),
):
    recipient = db.query(Recipient).filter(Recipient.id == recipient_id).first()
    if not recipient:
        raise HTTPException(404, "Recipient not found.")

    valid = {"WAITING", "MATCHED", "TRANSPLANTED"}
    if body.status.upper() not in valid:
        raise HTTPException(400, f"Invalid status. Choose from: {valid}")

    recipient.status = body.status.upper()
    audit = AuditLog(
        user_id=user.id,
        action="RECIPIENT_STATUS_UPDATED",
        target=recipient_id,
        meta={"patient_code": recipient.patient_code, "new_status": body.status},
    )
    db.add(audit)
    db.commit()
    return {"status": "UPDATED", "recipient_id": recipient_id, "new_status": recipient.status}


# ─── Helper ──────────────────────────────────────────────────────────────────

def _format_recipient(r: Recipient) -> dict:
    return {
        "id": r.id,
        "patient_code": r.patient_code,
        "organ_needed": r.organ_needed,
        "blood_group": r.blood_group,
        "hla_a": r.hla_a, "hla_b": r.hla_b, "hla_c": r.hla_c,
        "hla_dr": r.hla_dr, "hla_dq": r.hla_dq,
        "pra_percentage": r.pra_percentage,
        "urgency_level": r.urgency_level,
        "status": r.status,
        "registered_at": r.registered_at.isoformat() if r.registered_at else None,
        "additional_notes": r.additional_notes,
    }
