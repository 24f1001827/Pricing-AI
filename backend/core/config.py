from dotenv import load_dotenv
import os

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
E2B_API_KEY = os.getenv("E2B_API_KEY")
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI")
SECRET_KEY = os.getenv("SECRET_KEY")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
RUN_SCHEDULER = os.getenv("RUN_SCHEDULER", "false").lower() == "true"
SCHEDULER_TIMEZONE = os.getenv("SCHEDULER_TIMEZONE", "Asia/Kolkata")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", str(FRONTEND_URL.startswith("https://"))).lower() == "true"
ALLOW_REGISTRATION = os.getenv("ALLOW_REGISTRATION", "false").lower() == "true"
INITIAL_ADMIN_EMAIL = os.getenv("INITIAL_ADMIN_EMAIL", "").strip().lower()
INITIAL_ADMIN_PASSWORD = os.getenv("INITIAL_ADMIN_PASSWORD", "")
INITIAL_ADMIN_NAME = os.getenv("INITIAL_ADMIN_NAME", "Administrator").strip()
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").strip().lower()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Retraining thresholds
RETRAIN_NEW_DATA_THRESHOLD = float(os.getenv("RETRAIN_NEW_DATA_THRESHOLD", "0.08"))
RETRAIN_ERROR_THRESHOLD = float(os.getenv("RETRAIN_ERROR_THRESHOLD", "0.20"))
RETRAIN_DRIFT_THRESHOLD = float(os.getenv("RETRAIN_DRIFT_THRESHOLD", "0.50"))
MIN_RECORDS_TO_TRAIN = int(os.getenv("MIN_RECORDS_TO_TRAIN", "30"))

# Operational limits
TRAINING_STALE_MINUTES = int(os.getenv("TRAINING_STALE_MINUTES", "30"))
AUTH_RATE_LIMIT_PER_MINUTE = int(os.getenv("AUTH_RATE_LIMIT_PER_MINUTE", "20"))
DATA_DIR = os.getenv("DATA_DIR", "data")


def validate_runtime_config() -> None:
    """Fail fast on missing critical security/database settings."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL must be configured")
    if not SECRET_KEY or SECRET_KEY.startswith("replace-with"):
        raise RuntimeError("SECRET_KEY must be configured with a strong random secret")
