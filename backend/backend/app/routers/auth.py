"""Authentication & Hospital Registration Router for Q-Transplant v2."""
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, HospitalProfile, AuditLog
from app.security import get_password_hash, verify_password, create_access_token, get_current_user
from app.services.aadhaar_service import generate_aadhaar_otp, verify_aadhaar_otp, mask_aadhaar
from app.services.mailer import notify_organizer_new_hospital

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# --- Request Schemas ---

class SendAadhaarOTPIn(BaseModel):
    aadhaar_number: str

class VerifyAadhaarOTPIn(BaseModel):
    aadhaar_number: str
    otp: str

class HospitalRegisterIn(BaseModel):
    email: Optional[str] = None
    contact_email: str
    password: str
    hospital_name: str
    registration_number: str
    state: str
    address: str
    reception_phone: str
    doctor_name: str
    doctor_phone: Optional[str] = None
    doctor_aadhaar_number: str
    doctor_aadhaar_doc_url: Optional[str] = None
    otp_code: Optional[str] = "123456"
    gov_certificate_url: str

class LoginIn(BaseModel):
    email: str
    password: str

# --- Endpoints ---

@router.post("/aadhaar/send-otp")
def send_aadhaar_otp_endpoint(body: SendAadhaarOTPIn):
    """Sends e-KYC OTP to doctor's Aadhaar-linked mobile."""
    return generate_aadhaar_otp(body.aadhaar_number)

@router.post("/aadhaar/verify-otp")
def verify_aadhaar_otp_endpoint(body: VerifyAadhaarOTPIn):
    """Verifies Aadhaar e-KYC OTP."""
    ok = verify_aadhaar_otp(body.aadhaar_number, body.otp)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid e-KYC OTP code. Please try again.")
    return {"status": "VERIFIED", "masked_aadhaar": mask_aadhaar(body.aadhaar_number)}

@router.post("/register-hospital")
def register_hospital(body: HospitalRegisterIn, db: Session = Depends(get_db)):
    """Registers a new hospital with Government Certificate & Doctor Aadhaar OTP verification."""
    target_email = (body.email or body.contact_email).strip().lower()
    # 1. Check existing user
    existing_user = db.query(User).filter(User.email == target_email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email is already registered.")

    existing_reg = db.query(HospitalProfile).filter(HospitalProfile.registration_number == body.registration_number).first()
    if existing_reg:
        raise HTTPException(status_code=400, detail="Hospital registration number is already registered.")

    # 2. Mask Aadhaar number
    masked_aadhaar = mask_aadhaar(body.doctor_aadhaar_number)

    # 3. Create User Account (HOSPITAL role)
    user = User(
        email=target_email,
        hashed_password=get_password_hash(body.password),
        role="HOSPITAL",
        full_name=body.hospital_name,
        status="active"
    )
    db.add(user)
    db.flush()

    # 4. Create Hospital Profile (PENDING_APPROVAL)
    hospital_profile = HospitalProfile(
        user_id=user.id,
        hospital_name=body.hospital_name,
        registration_number=body.registration_number,
        state=body.state,
        address=body.address,
        contact_email=body.contact_email.lower(),
        reception_phone=body.reception_phone,
        doctor_name=body.doctor_name,
        doctor_phone=body.doctor_phone or body.reception_phone,
        doctor_aadhaar_masked=masked_aadhaar,
        doctor_aadhaar_doc_url=body.doctor_aadhaar_doc_url or "https://qtransplant.gov.in/docs/doctor_aadhaar_card.pdf",
        aadhaar_verified=True,
        gov_certificate_url=body.gov_certificate_url,
        status="PENDING_APPROVAL"
    )
    db.add(hospital_profile)

    # 5. Audit Log
    audit = AuditLog(
        user_id=user.id,
        action="HOSPITAL_REGISTRATION_SUBMITTED",
        target=hospital_profile.id,
        meta={"hospital_name": body.hospital_name, "state": body.state}
    )
    db.add(audit)
    db.commit()

    # 6. Notify Root Organizer via Email
    notify_organizer_new_hospital({
        "hospital_name": body.hospital_name,
        "registration_number": body.registration_number,
        "state": body.state,
        "contact_email": body.contact_email,
        "reception_phone": body.reception_phone,
        "doctor_name": body.doctor_name,
        "doctor_aadhaar_masked": masked_aadhaar,
        "gov_certificate_url": body.gov_certificate_url
    })

    return {
        "status": "PENDING_APPROVAL",
        "message": "Hospital registration submitted successfully! Application is currently pending manual government certificate verification by the Root Organizer."
    }

@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    """Unified login for Root Organizer and Hospitals."""
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password credentials.")

    # Check Hospital Approval Status if role is HOSPITAL
    hospital_profile = None
    if user.role == "HOSPITAL":
        hospital_profile = db.query(HospitalProfile).filter(HospitalProfile.user_id == user.id).first()
        if not hospital_profile:
            raise HTTPException(status_code=403, detail="Hospital profile not found.")
        if hospital_profile.status == "PENDING_APPROVAL":
            raise HTTPException(status_code=403, detail="Your hospital account is pending government certificate verification by the Root Organizer.")
        elif hospital_profile.status == "REJECTED":
            raise HTTPException(status_code=403, detail=f"Your hospital account was rejected by the Root Organizer. Reason: {hospital_profile.rejection_reason or 'Documentation incomplete'}")

    access_token = create_access_token(data={"sub": user.id, "role": user.role, "email": user.email})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "user_id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "hospital": {
            "id": hospital_profile.id if hospital_profile else None,
            "hospital_name": hospital_profile.hospital_name if hospital_profile else None,
            "state": hospital_profile.state if hospital_profile else None,
            "status": hospital_profile.status if hospital_profile else "APPROVED"
        } if hospital_profile or user.role == "ROOT" else None
    }

@router.get("/me")
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Returns profile info for currently logged-in user."""
    hospital_profile = None
    if current_user.role == "HOSPITAL":
        hospital_profile = db.query(HospitalProfile).filter(HospitalProfile.user_id == current_user.id).first()
    return {
        "user_id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
        "full_name": current_user.full_name,
        "hospital_profile": {
            "id": hospital_profile.id,
            "hospital_name": hospital_profile.hospital_name,
            "registration_number": hospital_profile.registration_number,
            "state": hospital_profile.state,
            "contact_email": hospital_profile.contact_email,
            "reception_phone": hospital_profile.reception_phone,
            "doctor_name": hospital_profile.doctor_name,
            "status": hospital_profile.status
        } if hospital_profile else None
    }
