"""Automated Email Notification Dispatcher Service."""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import settings

logger = logging.getLogger("qtransplant.mailer")

def send_email_notification(recipient_email: str, subject: str, body: str) -> bool:
    """Logs and dispatches email notifications via SMTP with console log fallback."""
    logger.info(f"========== DISPATCHING EMAIL ==========")
    logger.info(f"TO: {recipient_email}")
    logger.info(f"SUBJECT: {subject}")
    logger.info(f"BODY:\n{body}")
    logger.info(f"=======================================")

    sender_email = settings.ORGANIZER_EMAIL or "aravindhkmc@gmail.com"
    app_password = settings.ORGANIZER_APP_PASSWORD or "gayt lske btdx igtv"
    app_password_clean = app_password.replace(" ", "")

    if sender_email and app_password_clean:
        try:
            msg = MIMEMultipart()
            msg['From'] = f"Q-Transplant Network <{sender_email}>"
            msg['To'] = recipient_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
                server.starttls()
                server.login(sender_email, app_password_clean)
                server.send_message(msg)
            logger.info(f"Successfully sent live email to {recipient_email} via SMTP.")
            return True
        except Exception as e:
            logger.warning(f"SMTP delivery attempt to {recipient_email} notice: {e}. (Logged to console fallback)")
            return True
    return True

def notify_organizer_new_hospital(hospital_data: dict) -> bool:
    """Dispatches alert to Root Organizer when a new hospital submits registration."""
    root_email = "aravindhkmc@gmail.com"
    subject = f"NEW HOSPITAL REGISTRATION: {hospital_data.get('hospital_name')} ({hospital_data.get('state')})"
    body = f"""
[GOVERNMENT ORGAN ALLOCATION NETWORK - ROOT NOTICE]

A new hospital has submitted registration for government accreditation verification.

HOSPITAL DETAILS:
----------------------------------------
Hospital Name: {hospital_data.get('hospital_name')}
State Registration Code: {hospital_data.get('registration_number')}
State / Region: {hospital_data.get('state')}
Contact Email: {hospital_data.get('contact_email')}
Receptionist Phone: {hospital_data.get('reception_phone')}

DOCTOR / NODAL OFFICER DETAILS:
----------------------------------------
Doctor Name: {hospital_data.get('doctor_name')}
Doctor Mobile Phone: {hospital_data.get('doctor_phone')}
Aadhaar Masked ID: {hospital_data.get('doctor_aadhaar_masked')}
Doctor Aadhaar Doc: {hospital_data.get('doctor_aadhaar_doc_url')}
Govt Accreditation Certificate: {hospital_data.get('gov_certificate_url')}

Action Required: Please log into the Root Organizer Portal to inspect government certificates and Doctor Aadhaar documentation to Approve/Reject this application.
"""
    return send_email_notification(root_email, subject, body)

def notify_hospital_approval_status(hospital_email: str, hospital_name: str, status: str, reason: str = None) -> bool:
    """Notifies hospital of approval or rejection by Root Organizer."""
    if status.upper() == "APPROVED":
        subject = f"ACCREDITATION APPROVED: Welcome to Q-Transplant Network - {hospital_name}"
        body = f"""
Dear {hospital_name} Nodal Team,

We are pleased to inform you that your Government Accreditation Certificate and Nodal Doctor Aadhaar verification have been REVIEWED AND APPROVED by the Root Organizer.

Your hospital account is now ACTIVE. You can now log into the portal to:
1. Upload donor organ datasets (single entry or Bulk CSV Import).
2. Perform high-efficiency organ match searches.
3. Access holding hospital contact details for direct organ transfer requests.

Portal Login: http://localhost:8000/#/login

Thank you for contributing to the life-saving organ allocation network.
"""
    else:
        subject = f"APPLICATION UPDATE: Accreditation Status for {hospital_name}"
        body = f"""
Dear {hospital_name} Nodal Team,

Your hospital registration application has been REVIEWED by the Root Organizer.

Status: REJECTED
Reason: {reason or 'Government certificate verification failed or incomplete credentials provided.'}

If you believe this is an error or wish to re-submit updated government documentation, please contact aravindhkmc@gmail.com.
"""
    return send_email_notification(hospital_email, subject, body)
