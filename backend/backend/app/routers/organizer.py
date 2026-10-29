"""Root Organizer Router for Q-Transplant v4."""
import csv
import io
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, HospitalProfile, AutonomousIncidentLog, AuditLog, Donor, Recipient
from app.security import require_role
from app.services.mailer import notify_hospital_approval_status
from app.services.autonomous_failover import check_and_execute_autonomous_failover

router = APIRouter(prefix="/api/v1/organizer", tags=["Root Organizer"])

class RejectHospitalIn(BaseModel):
    reason: Optional[str] = "Government certificate verification incomplete or rejected."

@router.get("/pending-hospitals")
def get_pending_hospitals(user: User = Depends(require_role("ROOT")), db: Session = Depends(get_db)):
    """Returns list of hospital applications pending manual government certificate verification."""
    hospitals = db.query(HospitalProfile).filter(HospitalProfile.status == "PENDING_APPROVAL").order_by(HospitalProfile.created_at.desc()).all()
    return hospitals

@router.get("/hospitals")
def get_all_hospitals(user: User = Depends(require_role("ROOT")), db: Session = Depends(get_db)):
    """Returns all registered hospitals across the network."""
    hospitals = db.query(HospitalProfile).order_by(HospitalProfile.created_at.desc()).all()
    return hospitals

@router.post("/hospitals/{hospital_id}/approve")
def approve_hospital(hospital_id: str, user: User = Depends(require_role("ROOT")), db: Session = Depends(get_db)):
    """Approves a hospital application after manual government certificate inspection."""
    hospital = db.query(HospitalProfile).filter(HospitalProfile.id == hospital_id).first()
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital record not found.")

    hospital.status = "APPROVED"
    hospital.rejection_reason = None

    # Audit log
    audit = AuditLog(
        user_id=user.id,
        action="ROOT_APPROVED_HOSPITAL",
        target=hospital.id,
        meta={"hospital_name": hospital.hospital_name, "registration_number": hospital.registration_number}
    )
    db.add(audit)
    db.commit()

    # Dispatch Automated Approval Email
    notify_hospital_approval_status(hospital.contact_email, hospital.hospital_name, "APPROVED")

    return {"status": "APPROVED", "message": f"Hospital '{hospital.hospital_name}' has been successfully approved!"}

@router.post("/hospitals/{hospital_id}/reject")
def reject_hospital(hospital_id: str, body: RejectHospitalIn, user: User = Depends(require_role("ROOT")), db: Session = Depends(get_db)):
    """Rejects a hospital application with specified reason."""
    hospital = db.query(HospitalProfile).filter(HospitalProfile.id == hospital_id).first()
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital record not found.")

    hospital.status = "REJECTED"
    hospital.rejection_reason = body.reason

    # Audit log
    audit = AuditLog(
        user_id=user.id,
        action="ROOT_REJECTED_HOSPITAL",
        target=hospital.id,
        meta={"hospital_name": hospital.hospital_name, "reason": body.reason}
    )
    db.add(audit)
    db.commit()

    # Dispatch Automated Rejection Email
    notify_hospital_approval_status(hospital.contact_email, hospital.hospital_name, "REJECTED", body.reason)

    return {"status": "REJECTED", "message": f"Hospital '{hospital.hospital_name}' application has been rejected."}

@router.get("/failover-incidents")
def get_failover_incidents(user: User = Depends(require_role("ROOT")), db: Session = Depends(get_db)):
    """Returns log of ESP32 Autonomous Failover incidents triggered by 10-minute organizer timeouts."""
    incidents = db.query(AutonomousIncidentLog).order_by(AutonomousIncidentLog.triggered_at.desc()).all()
    return incidents

@router.post("/trigger-failover")
def trigger_failover_scan(user: User = Depends(require_role("ROOT")), db: Session = Depends(get_db)):
    """Manually triggers ESP32 Autonomous Failover engine scan."""
    results = check_and_execute_autonomous_failover(db)
    return {"status": "COMPLETED", "incidents_executed": results}

@router.get("/audit-logs")
def get_audit_logs(user: User = Depends(require_role("ROOT")), db: Session = Depends(get_db)):
    """Returns global system audit logs."""
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(100).all()
    return logs

@router.get("/hospital-datasets")
def get_hospital_datasets(user: User = Depends(require_role("ROOT")), db: Session = Depends(get_db)):
    """Returns all hospitals grouped with their complete donor organ datasets."""
    hospitals = db.query(HospitalProfile).order_by(HospitalProfile.hospital_name.asc()).all()
    result = []
    for h in hospitals:
        donors = db.query(Donor).filter(Donor.hospital_id == h.id).order_by(Donor.created_at.desc()).all()
        result.append({
            "hospital_id": h.id,
            "hospital_name": h.hospital_name,
            "registration_number": h.registration_number,
            "state": h.state,
            "contact_email": h.contact_email,
            "reception_phone": h.reception_phone,
            "status": h.status,
            "donor_count": len(donors),
            "donors": [
                _donor_row(d)
                for d in donors
            ]
        })
    return result


@router.get("/export-donors-csv", summary="Download complete national donor dataset as CSV/Excel")
def export_donors_csv(user: User = Depends(require_role("ROOT")), db: Session = Depends(get_db)):
    """Generates and streams a full CSV spreadsheet of all donors nationwide across all accredited hospitals."""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write Excel/CSV Header
    writer.writerow([
        "Donor_ID", "Hospital_Name", "State", "Registration_No", 
        "Organ_Type", "Blood_Group", "Rh_Factor", 
        "HLA_A", "HLA_B", "HLA_C", "HLA_DR", "HLA_DQ", 
        "Age", "Gender", "Health_Status", 
        "Stored_Viability_Hrs", "Realtime_Viability_Hrs", "Allocation_Status", "Uploaded_At"
    ])
    
    donors = db.query(Donor).order_by(Donor.created_at.desc()).all()
    now = datetime.now(timezone.utc)
    
    for d in donors:
        hosp = db.query(HospitalProfile).filter(HospitalProfile.id == d.hospital_id).first()
        uploaded = d.uploaded_at or d.created_at
        if uploaded and uploaded.tzinfo is None:
            uploaded = uploaded.replace(tzinfo=timezone.utc)
        elapsed_hrs = (now - uploaded).total_seconds() / 3600.0 if uploaded else 0
        actual_viability = max(0.0, round(d.viability_hours_remaining - elapsed_hrs, 1))
        
        status_str = "ALLOCATED" if d.is_allocated else ("EXPIRED" if actual_viability == 0 else "VIABLE / AVAILABLE")
        
        writer.writerow([
            d.id,
            hosp.hospital_name if hosp else "Unknown",
            hosp.state if hosp else "N/A",
            hosp.registration_number if hosp else "N/A",
            d.organ_type,
            d.blood_group,
            d.rh_factor or "+",
            d.hla_a or "N/A",
            d.hla_b or "N/A",
            d.hla_c or "N/A",
            d.hla_dr or "N/A",
            d.hla_dq or "N/A",
            d.age or "N/A",
            d.gender or "N/A",
            d.health_status or "OPTIMAL",
            d.viability_hours_remaining,
            actual_viability,
            status_str,
            uploaded.isoformat() if uploaded else ""
        ])
    
    csv_content = output.getvalue()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=national_organ_donors_dataset.csv"
        }
    )

@router.get("/audit-ledger", summary="SHA-256 cryptographic audit ledger")
def get_audit_ledger(user: User = Depends(require_role("ROOT"))):
    from app.audit_ledger import audit_ledger
    return {
        "status": "SECURE",
        "chain_valid": audit_ledger.is_chain_valid(),
        "total_blocks": audit_ledger.total_blocks,
        "ledger": audit_ledger.get_chain_dicts(),
    }


@router.get("/national-waiting-list", summary="National recipient waiting queue grouped by organ type")
def get_national_waiting_list(
    user: User = Depends(require_role("ROOT")),
    db: Session = Depends(get_db),
):
    """Returns all WAITING recipients nationwide, grouped by organ type, with urgency breakdown."""
    recipients = db.query(Recipient).filter(Recipient.status == "WAITING").all()
    grouped: dict = {}
    for r in recipients:
        hosp = db.query(HospitalProfile).filter(HospitalProfile.id == r.hospital_id).first()
        organ = r.organ_needed
        if organ not in grouped:
            grouped[organ] = {"organ": organ, "total": 0, "CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "patients": []}
        grouped[organ]["total"] += 1
        grouped[organ][r.urgency_level] = grouped[organ].get(r.urgency_level, 0) + 1
        grouped[organ]["patients"].append({
            "recipient_id": r.id,
            "patient_code": r.patient_code,
            "blood_group": r.blood_group,
            "urgency_level": r.urgency_level,
            "pra_percentage": r.pra_percentage,
            "registered_at": r.registered_at.isoformat() if r.registered_at else None,
            "hospital_name": hosp.hospital_name if hosp else "Unknown",
            "hospital_state": hosp.state if hosp else "Unknown",
        })
    # Sort each organ group: CRITICAL first
    urgency_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}
    for g in grouped.values():
        g["patients"].sort(key=lambda x: urgency_order.get(x["urgency_level"], 3))
    return {
        "total_waiting": len(recipients),
        "by_organ": list(grouped.values()),
    }


@router.get("/full-database-dump", summary="Root DB Inspector: Full schema dump of all system tables")
def full_database_dump(user: User = Depends(require_role("ROOT")), db: Session = Depends(get_db)):
    """Returns complete database tables dump for the System Database Explorer."""
    from app.audit_ledger import audit_ledger
    
    hospitals = db.query(HospitalProfile).order_by(HospitalProfile.hospital_name.asc()).all()
    donors = db.query(Donor).order_by(Donor.created_at.desc()).all()
    recipients = db.query(Recipient).order_by(Recipient.registered_at.desc()).all()
    users = db.query(User).all()
    incidents = db.query(AutonomousIncidentLog).order_by(AutonomousIncidentLog.triggered_at.desc()).all()
    
    hosp_map = {h.id: h.hospital_name for h in hospitals}
    
    hospitals_dump = [
        {
            "id": h.id,
            "hospital_name": h.hospital_name,
            "registration_number": h.registration_number,
            "state": h.state,
            "contact_email": h.contact_email,
            "reception_phone": h.reception_phone,
            "doctor_name": getattr(h, "doctor_name", "N/A"),
            "doctor_phone": getattr(h, "doctor_phone", "N/A"),
            "status": h.status,
            "latitude": h.latitude,
            "longitude": h.longitude,
            "created_at": h.created_at.isoformat() if h.created_at else None
        } for h in hospitals
    ]
    
    donors_dump = []
    for d in donors:
        row = _donor_row(d)
        row["hospital_name"] = hosp_map.get(d.hospital_id, "Unknown Hospital")
        donors_dump.append(row)
        
    recipients_dump = [
        {
            "id": r.id,
            "patient_code": r.patient_code,
            "hospital_id": r.hospital_id,
            "hospital_name": hosp_map.get(r.hospital_id, "Unknown Hospital"),
            "organ_needed": r.organ_needed,
            "blood_group": r.blood_group,
            "hla_a": r.hla_a, "hla_b": r.hla_b, "hla_c": r.hla_c,
            "hla_dr": r.hla_dr, "hla_dq": r.hla_dq,
            "pra_percentage": r.pra_percentage,
            "urgency_level": r.urgency_level,
            "status": r.status,
            "registered_at": r.registered_at.isoformat() if r.registered_at else None,
            "additional_notes": r.additional_notes
        } for r in recipients
    ]
    
    users_dump = [
        {
            "id": u.id,
            "email": u.email,
            "role": u.role,
            "full_name": u.full_name,
            "status": u.status
        } for u in users
    ]
    
    return {
        "db_engine": "SQLite / PostgreSQL Relational Database Engine (Q-Transplant v4)",
        "tables_count": 5,
        "summary": {
            "hospitals_count": len(hospitals_dump),
            "donors_count": len(donors_dump),
            "recipients_count": len(recipients_dump),
            "users_count": len(users_dump),
            "ledger_blocks": audit_ledger.total_blocks,
            "incidents_count": len(incidents)
        },
        "tables": {
            "hospitals": hospitals_dump,
            "donors": donors_dump,
            "recipients": recipients_dump,
            "users": users_dump,
            "ledger": audit_ledger.get_chain_dicts()
        }
    }


def _donor_row(d: Donor) -> dict:
    """Format a donor row with real-time viability decay."""
    now = datetime.now(timezone.utc)
    uploaded = d.uploaded_at or d.created_at
    if uploaded and uploaded.tzinfo is None:
        uploaded = uploaded.replace(tzinfo=timezone.utc)
    elapsed_hrs = (now - uploaded).total_seconds() / 3600.0 if uploaded else 0
    actual_viability = max(0.0, round(d.viability_hours_remaining - elapsed_hrs, 1))
    return {
        "id": d.id,
        "organ_type": d.organ_type,
        "blood_group": d.blood_group,
        "rh_factor": d.rh_factor,
        "hla_a": d.hla_a, "hla_b": d.hla_b, "hla_c": d.hla_c,
        "hla_dr": d.hla_dr, "hla_dq": d.hla_dq,
        "age": d.age, "gender": d.gender,
        "health_status": d.health_status,
        "viability_hours_stored": d.viability_hours_remaining,
        "viability_hours_actual": actual_viability,
        "is_allocated": bool(d.is_allocated),
        "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }
