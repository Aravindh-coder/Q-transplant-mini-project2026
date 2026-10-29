"""Donor Registry & Bulk CSV Ingestion Router for Q-Transplant v2."""
import csv
import io
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, HospitalProfile, Donor, AuditLog
from app.security import require_role, get_current_user

router = APIRouter(prefix="/api/v1/donors", tags=["donors"])

class SingleDonorIn(BaseModel):
    organ_type: str
    blood_group: str
    rh_factor: Optional[str] = "+"
    hla_a: Optional[str] = None
    hla_b: Optional[str] = None
    hla_c: Optional[str] = None
    hla_dr: Optional[str] = None
    hla_dq: Optional[str] = None
    age: Optional[int] = 35
    gender: Optional[str] = "M"
    health_status: Optional[str] = "Optimal"
    viability_hours_remaining: Optional[float] = 24.0

@router.post("")
def add_single_donor(body: SingleDonorIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Registers a single donor organ record for approved hospital or Root Organizer."""
    if user.role not in ("HOSPITAL", "ROOT"):
        raise HTTPException(status_code=403, detail="Access denied.")

    hospital = None
    if user.role == "HOSPITAL":
        hospital = db.query(HospitalProfile).filter(HospitalProfile.user_id == user.id).first()
        if not hospital or hospital.status != "APPROVED":
            raise HTTPException(status_code=403, detail="Hospital account must be APPROVED to upload donors.")
    else:
        hospital = db.query(HospitalProfile).filter(HospitalProfile.status == "APPROVED").first()
        if not hospital:
            raise HTTPException(status_code=400, detail="No approved hospital exists yet to attach donor record.")

    donor = Donor(
        hospital_id=hospital.id,
        organ_type=body.organ_type.strip().capitalize(),
        blood_group=body.blood_group.strip().upper(),
        rh_factor=body.rh_factor.strip(),
        hla_a=body.hla_a,
        hla_b=body.hla_b,
        hla_c=body.hla_c,
        hla_dr=body.hla_dr,
        hla_dq=body.hla_dq,
        age=body.age,
        gender=body.gender,
        health_status=body.health_status,
        viability_hours_remaining=body.viability_hours_remaining
    )
    db.add(donor)

    audit = AuditLog(
        user_id=user.id,
        action="DONOR_ORGAN_UPLOADED",
        target=donor.id,
        meta={"organ": body.organ_type, "blood_group": body.blood_group, "hospital": hospital.hospital_name}
    )
    db.add(audit)
    db.commit()

    return {"status": "SUCCESS", "donor_id": donor.id, "message": f"{body.organ_type} donor record added successfully!"}

@router.post("/import-csv")
def bulk_import_donors_csv(file: UploadFile = File(...), hospital_id: Optional[str] = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Bulk ingests donor organ datasets from a CSV file for approved hospitals or Root Organizer."""
    if user.role not in ("HOSPITAL", "ROOT"):
        raise HTTPException(status_code=403, detail="Access denied.")

    hospital = None
    if user.role == "HOSPITAL":
        hospital = db.query(HospitalProfile).filter(HospitalProfile.user_id == user.id).first()
        if not hospital or hospital.status != "APPROVED":
            raise HTTPException(status_code=403, detail="Hospital account must be APPROVED to upload CSV donor datasets.")
    else:
        if hospital_id:
            hospital = db.query(HospitalProfile).filter(HospitalProfile.id == hospital_id).first()
        if not hospital:
            hospital = db.query(HospitalProfile).filter(HospitalProfile.status == "APPROVED").first()
        if not hospital:
            raise HTTPException(status_code=400, detail="No approved hospital exists yet to attach CSV dataset.")

    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a CSV format file (.csv).")

    contents = file.file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(contents))

    imported_count = 0
    errors = []

    for idx, row in enumerate(reader, start=1):
        try:
            organ = row.get("organ_type") or row.get("organ") or row.get("Organ")
            blood = row.get("blood_group") or row.get("blood") or row.get("BloodGroup")
            if not organ or not blood:
                continue

            donor = Donor(
                hospital_id=hospital.id,
                organ_type=str(organ).strip().capitalize(),
                blood_group=str(blood).strip().upper(),
                rh_factor=str(row.get("rh_factor", "+")).strip(),
                hla_a=str(row.get("hla_a", "")).strip() or None,
                hla_b=str(row.get("hla_b", "")).strip() or None,
                hla_c=str(row.get("hla_c", "")).strip() or None,
                hla_dr=str(row.get("hla_dr", "")).strip() or None,
                hla_dq=str(row.get("hla_dq", "")).strip() or None,
                age=int(row.get("age", 35)) if row.get("age") else 35,
                gender=str(row.get("gender", "M")).strip(),
                health_status=str(row.get("health_status", "Optimal")).strip(),
                viability_hours_remaining=float(row.get("viability_hours_remaining", 24.0)) if row.get("viability_hours_remaining") else 24.0
            )
            db.add(donor)
            imported_count += 1
        except Exception as e:
            errors.append(f"Row {idx}: {str(e)}")

    db.commit()

    audit = AuditLog(
        user_id=user.id,
        action="BULK_CSV_DONORS_IMPORTED",
        target=hospital.id,
        meta={"imported_count": imported_count, "hospital_name": hospital.hospital_name}
    )
    db.add(audit)
    db.commit()

    return {
        "status": "SUCCESS",
        "imported_count": imported_count,
        "errors": errors[:5],
        "message": f"Successfully ingested {imported_count} donor records into unified dataset for {hospital.hospital_name}!"
    }

@router.get("/my-donors")
def get_my_hospital_donors(user: User = Depends(require_role("HOSPITAL")), db: Session = Depends(get_db)):
    """Returns list of donors registered by the currently logged-in hospital."""
    hospital = db.query(HospitalProfile).filter(HospitalProfile.user_id == user.id).first()
    if not hospital:
        return []
    donors = db.query(Donor).filter(Donor.hospital_id == hospital.id).order_by(Donor.created_at.desc()).all()
    return donors

@router.get("/all")
def get_all_global_donors(user: User = Depends(require_role("ROOT")), db: Session = Depends(get_db)):
    """Returns total donor pool across all hospitals (Root Organizer overview)."""
    donors = db.query(Donor).order_by(Donor.created_at.desc()).all()
    return donors
