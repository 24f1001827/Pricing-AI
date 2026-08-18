from dotenv import load_dotenv
import os

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
E2B_API_KEY = os.getenv("E2B_API_KEY")
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI")
SECRET_KEY = os.getenv("SECRET_KEY")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
RUN_SCHEDULER = os.getenv("RUN_SCHEDULER", "false").lower() == "true"
SCHEDULER_TIMEZONE = os.getenv("SCHEDULER_TIMEZONE", "Asia/Kolkata")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", str(FRONTEND_URL.startswith("https://"))).lower() == "true"
ALLOW_REGISTRATION = os.getenv("ALLOW_REGISTRATION", "false").lower() == "true"
INITIAL_ADMIN_EMAIL = os.getenv("INITIAL_ADMIN_EMAIL", "").strip().lower()
INITIAL_ADMIN_PASSWORD = os.getenv("INITIAL_ADMIN_PASSWORD", "")
INITIAL_ADMIN_NAME = os.getenv("INITIAL_ADMIN_NAME", "Administrator").strip()
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Retraining thresholds — easy to change
RETRAIN_NEW_DATA_THRESHOLD = float(os.getenv("RETRAIN_NEW_DATA_THRESHOLD", "0.08"))  # 8% more data
RETRAIN_ERROR_THRESHOLD = float(os.getenv("RETRAIN_ERROR_THRESHOLD", "0.20"))        # 20% MAE increase
RETRAIN_DRIFT_THRESHOLD = float(os.getenv("RETRAIN_DRIFT_THRESHOLD", "0.50"))        # 50% columns drifted
MIN_RECORDS_TO_TRAIN = int(os.getenv("MIN_RECORDS_TO_TRAIN", "30"))
