"""Q-Transplant configuration. Secrets are environment-only."""
import os
from dotenv import load_dotenv
load_dotenv()
BASE_DIR=os.path.abspath(os.path.join(os.path.dirname(__file__),"..","..",".."))
DEFAULT_DB_PATH=os.path.join(BASE_DIR,"qtransplant.db")

def _normalize_db_url(url:str)->str:
    # Aiven/Heroku-style URLs use the legacy "postgres://" scheme, which
    # modern SQLAlchemy refuses to parse — rewrite it to "postgresql://".
    if url.startswith("postgres://"):
        url="postgresql://"+url[len("postgres://"):]
    # Aiven requires SSL; add it if the caller didn't already specify a mode.
    if url.startswith("postgresql://") and "sslmode" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return url

class Settings:
    DATABASE_URL=_normalize_db_url(os.environ.get("DATABASE_URL",f"sqlite:///{DEFAULT_DB_PATH}"))
    JWT_SECRET=os.environ.get("JWT_SECRET","qtransplant_dev_secret_key_change_me")
    JWT_ALGO="HS256"
    ACCESS_TOKEN_MINUTES=int(os.environ.get("ACCESS_TOKEN_MINUTES",720))
    OTP_EXPIRY_MINUTES=int(os.environ.get("OTP_EXPIRY_MINUTES",10))
    ORGANIZER_EMAIL=os.environ.get("ORGANIZER_EMAIL","")
    ORGANIZER_APP_PASSWORD=os.environ.get("ORGANIZER_APP_PASSWORD","")
    ORGANIZER_BOOTSTRAP_EMAIL=os.environ.get("ORGANIZER_BOOTSTRAP_EMAIL","root@qtransplant.org")
    ORGANIZER_BOOTSTRAP_PASSWORD=os.environ.get("ORGANIZER_BOOTSTRAP_PASSWORD","root123")
    GROQ_API_KEY=os.environ.get("GROQ_API_KEY","")
    ANTHROPIC_API_KEY=os.environ.get("ANTHROPIC_API_KEY","")
    ALLOWED_ORIGINS=os.environ.get("ALLOWED_ORIGINS","*").split(",")
    LOGIN_RATE_LIMIT=int(os.environ.get("LOGIN_RATE_LIMIT",10))
    OTP_RATE_LIMIT=int(os.environ.get("OTP_RATE_LIMIT",5))
    UPLOAD_RATE_LIMIT=int(os.environ.get("UPLOAD_RATE_LIMIT",20))
    RATE_LIMIT_WINDOW_MINUTES=int(os.environ.get("RATE_LIMIT_WINDOW_MINUTES",15))
    MIN_PASSWORD_LENGTH=int(os.environ.get("MIN_PASSWORD_LENGTH",8))
settings=Settings()
if not settings.JWT_SECRET:
    settings.JWT_SECRET = "qtransplant_dev_secret_key_2026_v2"

if settings.DATABASE_URL.startswith("sqlite") and os.environ.get("RENDER"):
    import logging
    logging.getLogger("qtransplant.config").warning("DATABASE_URL is using sqlite on Render — data will reset on redeploy. Set a PostgreSQL DATABASE_URL in Render environment settings for persistent production storage.")

