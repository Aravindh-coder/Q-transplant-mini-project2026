"""Q-Transplant v4 relational database models."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Boolean, Float, Integer, ForeignKey, Text, JSON, Index
from app.database import Base

def uid(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=uid)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, index=True, nullable=False)  # "ROOT" or "HOSPITAL"
    full_name = Column(String, nullable=False)
    status = Column(String, index=True, default="active")
    created_at = Column(DateTime, index=True, default=now)

class RevokedToken(Base):
    __tablename__ = "revoked_tokens"
    id = Column(String, primary_key=True, default=uid)
    token_jti = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, index=True, nullable=False)
    created_at = Column(DateTime, default=now)

class HospitalProfile(Base):
    __tablename__ = "hospital_profiles"
    id = Column(String, primary_key=True, default=uid)
    user_id = Column(String, ForeignKey("users.id"), unique=True, index=True, nullable=False)
    hospital_name = Column(String, nullable=False, index=True)
    registration_number = Column(String, unique=True, index=True, nullable=False)
    state = Column(String, nullable=False)
    address = Column(String, nullable=False)
    contact_email = Column(String, nullable=False)
    reception_phone = Column(String, nullable=False)
    doctor_name = Column(String, nullable=False)
    doctor_phone = Column(String, nullable=True)
    doctor_aadhaar_masked = Column(String, nullable=False)
    doctor_aadhaar_doc_url = Column(String, nullable=True)
    aadhaar_verified = Column(Boolean, default=True)
    gov_certificate_url = Column(String, nullable=False)
    status = Column(String, index=True, default="PENDING_APPROVAL")  # PENDING_APPROVAL, APPROVED, REJECTED
    rejection_reason = Column(Text, nullable=True)
    # GIS Coordinates for transport-time calculation
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    created_at = Column(DateTime, index=True, default=now)

class Donor(Base):
    __tablename__ = "donors"
    id = Column(String, primary_key=True, default=uid)
    hospital_id = Column(String, ForeignKey("hospital_profiles.id"), index=True, nullable=False)
    organ_type = Column(String, nullable=False, index=True)
    blood_group = Column(String, nullable=False, index=True)
    rh_factor = Column(String, default="+")
    hla_a = Column(String, nullable=True)
    hla_b = Column(String, nullable=True)
    hla_c = Column(String, nullable=True)
    hla_dr = Column(String, nullable=True)
    hla_dq = Column(String, nullable=True)
    age = Column(Integer, nullable=True)
    gender = Column(String, nullable=True)
    health_status = Column(String, default="Optimal")
    viability_hours_remaining = Column(Float, default=24.0)
    # NEW: track when donor was uploaded so viability decays in real-time
    uploaded_at = Column(DateTime, index=True, default=now)
    # NEW: allocation lock — True once a hospital confirms they are proceeding
    is_allocated = Column(Boolean, default=False)
    allocated_to_hospital_id = Column(String, nullable=True)
    created_at = Column(DateTime, index=True, default=now)

class Recipient(Base):
    """Patient on the organ waiting list, registered by a hospital."""
    __tablename__ = "recipients"
    id = Column(String, primary_key=True, default=uid)
    hospital_id = Column(String, ForeignKey("hospital_profiles.id"), index=True, nullable=False)
    # Patient identity kept anonymized inside the platform
    patient_code = Column(String, nullable=False)  # e.g. PAT-AIIMS-001
    organ_needed = Column(String, nullable=False, index=True)
    blood_group = Column(String, nullable=False, index=True)
    rh_factor = Column(String, default="+")
    # Full HLA profile
    hla_a = Column(String, nullable=True)
    hla_b = Column(String, nullable=True)
    hla_c = Column(String, nullable=True)
    hla_dr = Column(String, nullable=True)
    hla_dq = Column(String, nullable=True)
    # Panel Reactive Antibody — sensitization level (0-100%)
    pra_percentage = Column(Float, default=0.0)
    urgency_level = Column(String, index=True, default="HIGH")  # CRITICAL, HIGH, MEDIUM
    additional_notes = Column(Text, nullable=True)
    status = Column(String, index=True, default="WAITING")  # WAITING, MATCHED, TRANSPLANTED
    registered_at = Column(DateTime, index=True, default=now)

class OrganRequest(Base):
    __tablename__ = "organ_requests"
    id = Column(String, primary_key=True, default=uid)
    requesting_hospital_id = Column(String, ForeignKey("hospital_profiles.id"), index=True, nullable=False)
    patient_name = Column(String, default="Anonymized Patient")
    organ_type = Column(String, nullable=False, index=True)
    blood_group = Column(String, nullable=False, index=True)
    rh_factor = Column(String, default="+")
    hla_a = Column(String, nullable=True)
    hla_b = Column(String, nullable=True)
    hla_c = Column(String, nullable=True)
    hla_dr = Column(String, nullable=True)
    hla_dq = Column(String, nullable=True)
    urgency_level = Column(String, index=True, default="HIGH")
    status = Column(String, index=True, default="OPEN")
    created_at = Column(DateTime, index=True, default=now)
    timeout_at = Column(DateTime, index=True, nullable=False)

class AutonomousIncidentLog(Base):
    __tablename__ = "autonomous_incident_logs"
    id = Column(String, primary_key=True, default=uid)
    request_id = Column(String, ForeignKey("organ_requests.id"), index=True, nullable=False)
    requesting_hospital_name = Column(String, nullable=False)
    matched_hospital_name = Column(String, nullable=False)
    organ_type = Column(String, nullable=False)
    match_efficiency_score = Column(Float, nullable=False)
    triggered_at = Column(DateTime, index=True, default=now)
    status = Column(String, default="DISPATCHED")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(String, primary_key=True, default=uid)
    user_id = Column(String, ForeignKey("users.id"), index=True, nullable=True)
    action = Column(String, index=True, nullable=False)
    target = Column(String, index=True, nullable=True)
    meta = Column(JSON, default=dict)
    ip_address = Column(String, nullable=True)
    created_at = Column(DateTime, index=True, default=now)

class AuditLedgerBlock(Base):
    """Persistent SHA-256 cryptographic audit ledger block."""
    __tablename__ = "audit_ledger_blocks"
    id = Column(String, primary_key=True, default=uid)
    block_index = Column(Integer, unique=True, nullable=False)
    action = Column(String, nullable=False)
    details = Column(JSON, default=dict)
    block_hash = Column(String, nullable=False)
    previous_hash = Column(String, nullable=False)
    timestamp = Column(Float, nullable=False)

class Document(Base):
    __tablename__ = "documents"
    id = Column(String, primary_key=True, default=uid)
    owner_user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)
    kind = Column(String, index=True, nullable=False)
    filename = Column(String, nullable=False)
    storage_path = Column(String, nullable=False)
    verification_status = Column(String, index=True, default="pending")
    uploaded_at = Column(DateTime, index=True, default=now)
