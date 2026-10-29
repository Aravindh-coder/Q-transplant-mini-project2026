"""ESP32 Autonomous Failover Engine (10-Minute Organizer Timeout)."""
from datetime import datetime, timezone
import logging
from sqlalchemy.orm import Session
from app.models import OrganRequest, Donor, HospitalProfile, AutonomousIncidentLog, AuditLog
from app.services.efficiency_engine import calculate_match_efficiency
from app.services.mailer import send_email_notification

logger = logging.getLogger("qtransplant.failover")

def check_and_execute_autonomous_failover(db: Session) -> list[dict]:
    """Scans for unacted urgent organ requests that have exceeded the 10-minute organizer timeout."""
    now = datetime.now(timezone.utc)
    expired_requests = db.query(OrganRequest).filter(
        OrganRequest.status == "OPEN",
        OrganRequest.timeout_at <= now
    ).all()

    executed_incidents = []

    for req in expired_requests:
        logger.info(f"ESP32 Autonomous Failover triggered for Urgent Request ID: {req.id}")
        
        # 1. Fetch Requesting Hospital Details
        req_hospital = db.query(HospitalProfile).filter(HospitalProfile.id == req.requesting_hospital_id).first()
        req_hospital_name = req_hospital.hospital_name if req_hospital else "Requesting Hospital"
        req_hospital_email = req_hospital.contact_email if req_hospital else "emergency@hospital.org"

        # 2. Query Unified Donor Pool across all approved hospitals
        donors = db.query(Donor).all()
        
        best_match = None
        highest_efficiency = 0.0

        recipient_spec = {
            "organ_type": req.organ_type,
            "blood_group": req.blood_group,
            "hla_a": req.hla_a,
            "hla_b": req.hla_b,
            "hla_c": req.hla_c,
            "hla_dr": req.hla_dr,
            "hla_dq": req.hla_dq
        }

        for donor in donors:
            # Exclude donors from the same requesting hospital if needed
            donor_spec = {
                "organ_type": donor.organ_type,
                "blood_group": donor.blood_group,
                "hla_a": donor.hla_a,
                "hla_b": donor.hla_b,
                "hla_c": donor.hla_c,
                "hla_dr": donor.hla_dr,
                "hla_dq": donor.hla_dq,
                "viability_hours_remaining": donor.viability_hours_remaining,
                "health_status": donor.health_status
            }
            res = calculate_match_efficiency(donor_spec, recipient_spec)
            score = res.get("efficiency_score", 0.0)
            if score > highest_efficiency:
                highest_efficiency = score
                best_match = (donor, res)

        if best_match and highest_efficiency >= 40.0:
            matched_donor, match_res = best_match
            matched_hospital = db.query(HospitalProfile).filter(HospitalProfile.id == matched_donor.hospital_id).first()
            matched_hospital_name = matched_hospital.hospital_name if matched_hospital else "Holding Medical Center"

            # 3. Update Request Status
            req.status = "AUTONOMOUS_FAILOVER"

            # 4. Record Autonomous Incident Audit
            incident = AutonomousIncidentLog(
                request_id=req.id,
                requesting_hospital_name=req_hospital_name,
                matched_hospital_name=matched_hospital_name,
                organ_type=req.organ_type,
                match_efficiency_score=highest_efficiency,
                status="DISPATCHED"
            )
            db.add(incident)
            
            # 5. Log System Audit
            audit = AuditLog(
                user_id="ESP32_FAILOVER_ENGINE",
                action="AUTONOMOUS_MATCH_EXECUTED",
                target=req.id,
                meta={
                    "efficiency_score": highest_efficiency,
                    "matched_hospital": matched_hospital_name,
                    "reason": "Root Organizer 10-Minute Timeout Exceeded"
                }
            )
            db.add(audit)
            db.commit()

            # 6. Automated Email Notification Dispatch
            email_body = f"""
[ESP32 AUTONOMOUS FAILOVER DISPATCH NOTICE]

Urgent Organ Request ID: {req.id}
Organ Required: {req.organ_type} ({req.blood_group})

Status: Organizer inactive for >10 minutes. ESP32 Autonomous Engine matched an organ with {highest_efficiency}% Match Efficiency.

MATCHED HOLDING HOSPITAL DETAILS:
----------------------------------------
Hospital Name: {matched_hospital_name}
State: {matched_hospital.state if matched_hospital else 'N/A'}
Address: {matched_hospital.address if matched_hospital else 'N/A'}
Receptionist Phone: {matched_hospital.reception_phone if matched_hospital else 'N/A'}
Emergency Email: {matched_hospital.contact_email if matched_hospital else 'N/A'}
Authorized Nodal Doctor: {matched_hospital.doctor_name if matched_hospital else 'N/A'}

Please contact the holding hospital immediately to arrange organ transport logistics.
"""
            send_email_notification(req_hospital_email, f"URGENT: ESP32 Autonomous Organ Match Dispatched ({highest_efficiency}%)", email_body)
            
            executed_incidents.append({
                "request_id": req.id,
                "requesting_hospital": req_hospital_name,
                "matched_hospital": matched_hospital_name,
                "efficiency_score": highest_efficiency,
                "status": "DISPATCHED"
            })
        else:
            # Mark timeout logged if no candidates found
            req.status = "AUTONOMOUS_FAILOVER_NO_MATCH"
            db.commit()

    return executed_incidents
