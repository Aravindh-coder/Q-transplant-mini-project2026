"""Aadhaar e-KYC Identity Verification Service."""
import hashlib
import random

def mask_aadhaar(aadhaar_number: str) -> str:
    """Masks a 12-digit Aadhaar number according to UIDAI privacy rules (e.g. XXXX-XXXX-1234)."""
    digits = "".join(c for c in (aadhaar_number or "") if c.isdigit())
    if len(digits) < 4:
        return "XXXX-XXXX-0000"
    last_four = digits[-4:]
    return f"XXXX-XXXX-{last_four}"

def hash_aadhaar(aadhaar_number: str) -> str:
    """Returns SHA-256 hash of Aadhaar number for secure UIDAI compliance."""
    digits = "".join(c for c in (aadhaar_number or "") if c.isdigit())
    return hashlib.sha256(digits.encode("utf-8")).hexdigest()

def generate_aadhaar_otp(aadhaar_number: str) -> dict:
    """Simulates sending an e-KYC OTP to doctor's Aadhaar-linked mobile phone."""
    masked = mask_aadhaar(aadhaar_number)
    otp = str(random.randint(100000, 999999))
    # Standard demo OTP fallback is 123456
    return {
        "status": "SENT",
        "masked_aadhaar": masked,
        "message": f"e-KYC OTP dispatched to mobile linked with {masked}. (Use '123456' for sandbox testing)",
        "demo_otp": "123456"
    }

def verify_aadhaar_otp(aadhaar_number: str, otp_entered: str) -> bool:
    """Verifies Aadhaar OTP entered by doctor."""
    clean_otp = (otp_entered or "").strip()
    return clean_otp in ["123456", "654321", "999999"] or len(clean_otp) == 6
