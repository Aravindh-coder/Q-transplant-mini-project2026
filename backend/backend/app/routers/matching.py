"""Q-Transplant v4 — Organ Matching Router.

All match searches now use:
  - Real-time viability decay (from uploaded_at timestamp)
  - GIS-adjusted viability (Haversine distance between hospitals)
  - Full 6-locus weighted HLA scoring
  - PRA crossmatch risk flagging
  - Organ allocation locking (confirm allocation)
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, HospitalProfile, Donor, OrganRequest, AuditLog
from app.security import require_role
from app.services.efficiency_engine import calculate_match_efficiency
from app.services.gis_engine import compute_gis_adjusted_viability

router = APIRouter(prefix="/api/v1/matching", tags=["Organ Matching"])


class OrganMatchSearchIn(BaseModel):
    organ_type: str
    blood_group: str
    rh_factor: Optional[str] = "+"
    hla_a: Optional[str] = None
    hla_b: Optional[str] = None
    hla_c: Optional[str] = None
    hla_dr: Optional[str] = None
    hla_dq: Optional[str] = None
    pra_percentage: Optional[float] = 0.0
    urgency_level: Optional[str] = "HIGH"
    min_efficiency_percentage: Optional[float] = 0.0


class UrgentRequestIn(BaseModel):
    organ_type: str
    blood_group: str
    rh_factor: Optional[str] = "+"
    hla_a: Optional[str] = None
    hla_b: Optional[str] = None
    hla_c: Optional[str] = None
    hla_dr: Optional[str] = None
    hla_dq: Optional[str] = None
    urgency_level: Optional[str] = "CRITICAL"
    patient_name: Optional[str] = "Anonymized Recipient"


@router.post("/search", summary="Run clinical multi-factor organ match search")
def search_organ_matches(
    body: OrganMatchSearchIn,
    user: User = Depends(require_role("HOSPITAL", "ROOT")),
    db: Session = Depends(get_db),
):
    """Runs the full clinical match engine across all unallocated donor organs.
    - Real-time viability decay from upload timestamp
    - GIS Haversine transport time subtracted from viability
    - 6-locus weighted HLA scoring (DR=12%, A=8%, B=8%, DQ=6%, C=4%)
    - PRA crossmatch risk flagging
    Only holding hospital contact info is exposed (donor identity hidden).
    """
    requesting_hospital = None
    if user.role == "HOSPITAL":
        requesting_hospital = db.query(HospitalProfile).filter(
            HospitalProfile.user_id == user.id
        ).first()
        if not requesting_hospital or requesting_hospital.status != "APPROVED":
            raise HTTPException(403, "Hospital must be APPROVED to run match searches.")

    recipient_spec = {
        "organ_type": body.organ_type,
        "blood_group": body.blood_group,
        "hla_a": body.hla_a, "hla_b": body.hla_b,
        "hla_c": body.hla_c, "hla_dr": body.hla_dr, "hla_dq": body.hla_dq,
    }

    # Fetch only unallocated donors
    donors = db.query(Donor).filter(Donor.is_allocated == False).all()
    now = datetime.now(timezone.utc)
    results = []

    for donor in donors:
        # ── Real-time viability decay ──────────────────────────────────────
        uploaded = donor.uploaded_at or donor.created_at
        if uploaded and uploaded.tzinfo is None:
            uploaded = uploaded.replace(tzinfo=timezone.utc)
        elapsed_hrs = (now - uploaded).total_seconds() / 3600.0 if uploaded else 0
        actual_viability = max(0.0, donor.viability_hours_remaining - elapsed_hrs)
        if actual_viability <= 0:
            continue

        # ── GIS distance calculation ───────────────────────────────────────
        holding_hospital = db.query(HospitalProfile).filter(
            HospitalProfile.id == donor.hospital_id
        ).first()
        if not holding_hospital:
            continue

        gis = compute_gis_adjusted_viability(
            stored_viability_hours=actual_viability,
            donor_lat=holding_hospital.latitude,
            donor_lon=holding_hospital.longitude,
            recipient_lat=requesting_hospital.latitude if requesting_hospital else None,
            recipient_lon=requesting_hospital.longitude if requesting_hospital else None,
            organ_type=donor.organ_type,
            donor_state=holding_hospital.state,
            recipient_state=requesting_hospital.state if requesting_hospital else "",
        )
        # ROOT users (no hospital profile) bypass GIS viability check — show all viable donors
        if requesting_hospital and not gis["is_viable"]:
            continue

        donor_spec = {
            "organ_type": donor.organ_type,
            "blood_group": donor.blood_group,
            "hla_a": donor.hla_a, "hla_b": donor.hla_b,
            "hla_c": donor.hla_c, "hla_dr": donor.hla_dr, "hla_dq": donor.hla_dq,
            "viability_hours_remaining": actual_viability,
            "health_status": donor.health_status,
        }

        metrics = calculate_match_efficiency(
            donor=donor_spec,
            recipient=recipient_spec,
            gis_data=gis,
            urgency_level=body.urgency_level,
            pra_percentage=body.pra_percentage or 0.0,
        )

        score = metrics.get("efficiency_score", 0.0)
        if score < body.min_efficiency_percentage or not metrics.get("is_compatible"):
            continue

        results.append({
            "donor_ref": f"DONOR-{donor.id[:8].upper()}",
            "donor_id": donor.id,
            "organ_type": donor.organ_type,
            "donor_blood_group": donor.blood_group,
            "efficiency_score_percentage": score,
            "score_breakdown": {
                "blood": metrics["blood_score"],
                "hla": metrics["hla_score"],
                "hla_pct": metrics["hla_percentage"],
                "viability": metrics["viability_score"],
                "urgency": metrics["urgency_score"],
                "pra_penalty": metrics["pra_penalty"],
            },
            "gis_info": {
                "distance_km": gis.get("distance_km"),
                "transport_hours": gis.get("transport_hours"),
                "actual_viability_stored_hrs": round(actual_viability, 1),
                "adjusted_viability_hours": gis.get("adjusted_viability_hours"),
                "gis_available": gis.get("gis_available"),
            },
            "pra_risk": metrics["pra_risk"],
            "pra_flag": metrics["pra_flag"],
            "pra_message": metrics["pra_message"],
            "viability_hours_remaining": gis.get("adjusted_viability_hours", actual_viability),
            "health_status": donor.health_status,
            "holding_hospital": {
                "hospital_id": holding_hospital.id,
                "hospital_name": holding_hospital.hospital_name,
                "registration_number": holding_hospital.registration_number,
                "state": holding_hospital.state,
                "address": holding_hospital.address,
                "reception_phone": holding_hospital.reception_phone,
                "contact_email": holding_hospital.contact_email,
                "authorized_doctor": holding_hospital.doctor_name,
            },
        })

    results.sort(key=lambda x: x["efficiency_score_percentage"], reverse=True)

    # Audit ledger block
    from app.audit_ledger import audit_ledger
    audit_ledger.add_block(
        action="MATCH_ENGINE_SEARCH_EXECUTED",
        details={
            "user_id": user.id, "user_role": user.role,
            "organ_type": body.organ_type, "blood_group": body.blood_group,
            "matches_found": len(results),
            "top_score": results[0]["efficiency_score_percentage"] if results else 0,
        },
    )

    audit = AuditLog(
        user_id=user.id, action="MATCH_SEARCH_EXECUTED",
        target=body.organ_type,
        meta={"organ": body.organ_type, "matches_found": len(results)},
    )
    db.add(audit)
    db.commit()

    return {
        "organ_type": body.organ_type,
        "recipient_blood_group": body.blood_group,
        "total_matches_found": len(results),
        "matches": results,
        "search_criteria": recipient_spec,
    }


@router.post("/allocate/{donor_id}", summary="Confirm organ allocation — locks the donor organ")
def confirm_allocation(
    donor_id: str,
    user: User = Depends(require_role("HOSPITAL", "ROOT")),
    db: Session = Depends(get_db),
):
    """Marks a donor organ as allocated. Prevents double-booking.
    Writes an immutable block to the audit ledger.
    """
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(404, "Donor organ not found.")
    if donor.is_allocated:
        raise HTTPException(409, "This organ has already been allocated to another recipient.")

    requesting_hospital = None
    if user.role == "HOSPITAL":
        requesting_hospital = db.query(HospitalProfile).filter(
            HospitalProfile.user_id == user.id
        ).first()

    donor.is_allocated = True
    donor.allocated_to_hospital_id = requesting_hospital.id if requesting_hospital else None

    holding_hospital = db.query(HospitalProfile).filter(
        HospitalProfile.id == donor.hospital_id
    ).first()

    from app.audit_ledger import audit_ledger
    audit_ledger.add_block(
        action="ORGAN_ALLOCATION_CONFIRMED",
        details={
            "donor_id": donor_id,
            "organ_type": donor.organ_type,
            "allocated_by_user": user.id,
            "allocated_to_hospital": requesting_hospital.hospital_name if requesting_hospital else "ROOT",
            "holding_hospital": holding_hospital.hospital_name if holding_hospital else "Unknown",
        },
    )

    audit = AuditLog(
        user_id=user.id, action="ORGAN_ALLOCATION_CONFIRMED",
        target=donor_id,
        meta={"organ_type": donor.organ_type, "hospital": requesting_hospital.hospital_name if requesting_hospital else "ROOT"},
    )
    db.add(audit)
    db.commit()

    # Send email alerts to both hospitals
    try:
        from app.services.mailer import notify_hospital_approval_status
        if requesting_hospital:
            notify_hospital_approval_status(
                requesting_hospital.contact_email,
                requesting_hospital.hospital_name,
                "ORGAN_ALLOCATED",
                f"Organ: {donor.organ_type} | Donor Hospital: {holding_hospital.hospital_name if holding_hospital else 'N/A'}"
            )
    except Exception:
        pass

    return {
        "status": "ALLOCATED",
        "donor_id": donor_id,
        "organ_type": donor.organ_type,
        "allocated_to": requesting_hospital.hospital_name if requesting_hospital else "ROOT",
        "message": f"✅ {donor.organ_type} organ successfully allocated and locked. Contact the holding hospital immediately to arrange transfer.",
    }


@router.post("/urgent-request", summary="Submit urgent organ request with 10-min ESP32 failover")
def create_urgent_organ_request(
    body: UrgentRequestIn,
    user: User = Depends(require_role("HOSPITAL")),
    db: Session = Depends(get_db),
):
    hospital = db.query(HospitalProfile).filter(HospitalProfile.user_id == user.id).first()
    if not hospital or hospital.status != "APPROVED":
        raise HTTPException(403, "Hospital must be APPROVED to submit urgent requests.")

    now = datetime.now(timezone.utc)
    req = OrganRequest(
        requesting_hospital_id=hospital.id,
        patient_name=body.patient_name or "Anonymized Recipient",
        organ_type=body.organ_type.strip().capitalize(),
        blood_group=body.blood_group.strip().upper(),
        rh_factor=body.rh_factor,
        hla_a=body.hla_a, hla_b=body.hla_b,
        hla_c=body.hla_c, hla_dr=body.hla_dr, hla_dq=body.hla_dq,
        urgency_level=body.urgency_level,
        status="OPEN",
        timeout_at=now + timedelta(minutes=10),
    )
    db.add(req)
    audit = AuditLog(
        user_id=user.id, action="URGENT_ORGAN_REQUEST_SUBMITTED",
        target=req.id,
        meta={"organ": body.organ_type, "urgency": body.urgency_level,
              "hospital": hospital.hospital_name},
    )
    db.add(audit)
    db.commit()

    return {
        "status": "OPEN",
        "request_id": req.id,
        "timeout_at": req.timeout_at.isoformat(),
        "message": (f"Urgent request for {body.organ_type} ({body.blood_group}) submitted. "
                    "If unacted within 10 minutes, the ESP32 Autonomous Failover Engine triggers automatically."),
    }


@router.get("/my-requests", summary="Hospital's own urgent request history")
def get_my_urgent_requests(
    user: User = Depends(require_role("HOSPITAL")),
    db: Session = Depends(get_db),
):
    hospital = db.query(HospitalProfile).filter(HospitalProfile.user_id == user.id).first()
    if not hospital:
        return []
    return db.query(OrganRequest).filter(
        OrganRequest.requesting_hospital_id == hospital.id
    ).order_by(OrganRequest.created_at.desc()).all()


@router.get("/all-requests", summary="Root: all urgent requests nationally")
def get_all_urgent_requests(
    user: User = Depends(require_role("ROOT")),
    db: Session = Depends(get_db),
):
    return db.query(OrganRequest).order_by(OrganRequest.created_at.desc()).all()
