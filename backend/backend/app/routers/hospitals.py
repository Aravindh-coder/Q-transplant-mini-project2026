"""Hospitals Directory Router for Q-Transplant v2."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, HospitalProfile
from app.security import get_current_user, require_role

router = APIRouter(prefix="/api/v1/hospitals", tags=["hospitals"])

@router.get("/directory")
def hospital_directory(db: Session = Depends(get_db)):
    """Returns directory of approved hospitals across the network."""
    hospitals = db.query(HospitalProfile).filter(HospitalProfile.status == "APPROVED").all()
    return [
        {
            "id": h.id,
            "hospital_name": h.hospital_name,
            "state": h.state,
            "address": h.address,
            "reception_phone": h.reception_phone,
            "contact_email": h.contact_email,
            "doctor_name": h.doctor_name
        }
        for h in hospitals
    ]

@router.get("/me")
def get_my_hospital_profile(user: User = Depends(require_role("HOSPITAL")), db: Session = Depends(get_db)):
    """Returns logged-in hospital's own profile."""
    profile = db.query(HospitalProfile).filter(HospitalProfile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Hospital profile not found.")
    return {
        "id": profile.id,
        "hospital_name": profile.hospital_name,
        "registration_number": profile.registration_number,
        "state": profile.state,
        "address": profile.address,
        "contact_email": profile.contact_email,
        "reception_phone": profile.reception_phone,
        "doctor_name": profile.doctor_name,
        "doctor_aadhaar_masked": profile.doctor_aadhaar_masked,
        "status": profile.status
    }
