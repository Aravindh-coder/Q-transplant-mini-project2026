from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Donor, HospitalProfile
from app.security import get_current_user
import uuid
import datetime

router = APIRouter(prefix="/api/v1/fhir", tags=["FHIR Interoperability"])

@router.get("/donors/{donor_id}", summary="Export Donor Record as HL7 FHIR R4 Bundle")
def export_donor_fhir(donor_id: str, db: Session = Depends(get_db)):
    donor = db.query(Donor).filter(Donor.id == donor_id).first()
    if not donor:
        raise HTTPException(status_code=404, detail="Donor organ record not found.")

    hospital = db.query(HospitalProfile).filter(HospitalProfile.id == donor.hospital_id).first()

    # Construct standard HL7 FHIR R4 Bundle (Specimen + Observation)
    fhir_bundle = {
        "resourceType": "Bundle",
        "id": f"bundle-donor-{donor.id}",
        "type": "collection",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "entry": [
            {
                "fullUrl": f"urn:uuid:hospital-{hospital.id if hospital else 'unknown'}",
                "resource": {
                    "resourceType": "Organization",
                    "id": hospital.id if hospital else "unknown",
                    "name": hospital.hospital_name if hospital else "Unknown Hospital",
                    "identifier": [
                        {
                            "system": "https://nnoto.gov.in/hospitals",
                            "value": hospital.registration_number if hospital else "N/A"
                        }
                    ],
                    "address": [
                        {
                            "text": hospital.address if hospital else "N/A",
                            "state": hospital.state if hospital else "N/A"
                        }
                    ]
                }
            },
            {
                "fullUrl": f"urn:uuid:organ-{donor.id}",
                "resource": {
                    "resourceType": "Specimen",
                    "id": donor.id,
                    "type": {
                        "coding": [
                            {
                                "system": "http://snomed.info/sct",
                                "code": "258384009",
                                "display": donor.organ_type
                            }
                        ],
                        "text": f"Human Organ: {donor.organ_type}"
                    },
                    "note": [
                        {"text": f"Blood Group: {donor.blood_group}"},
                        {"text": f"HLA-A: {donor.hla_a or 'N/A'}, HLA-B: {donor.hla_b or 'N/A'}"},
                        {"text": f"Remaining Cold Ischemic Viability: {donor.viability_hours_remaining} hours"}
                    ],
                    "status": "available" if not getattr(donor, 'is_allocated', False) else "unavailable"
                }
            }
        ]
    }
    return fhir_bundle
