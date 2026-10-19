import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Detect Vercel / serverless runtime environment
IS_VERCEL = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))

if IS_VERCEL:
    INSTANCE_DIR = Path("/tmp/instance")
    DEFAULT_UPLOAD_DIR = Path("/tmp/uploads")
else:
    INSTANCE_DIR = BASE_DIR / "instance"
    DEFAULT_UPLOAD_DIR = BASE_DIR / "instance" / "uploads"

try:
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    INSTANCE_DIR = Path("/tmp/instance")
    DEFAULT_UPLOAD_DIR = Path("/tmp/uploads")
    try:
        INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
        DEFAULT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

load_dotenv(BASE_DIR / ".env")

DEFAULT_DB_PATH = (INSTANCE_DIR / "interview_studio.db").as_posix()
raw_db_url = os.getenv("DATABASE_URL", "").strip()
if not raw_db_url or "sqlite:///instance/" in raw_db_url or raw_db_url == "sqlite:///instance/interview_studio.db":
    RESOLVED_DB_URL = f"sqlite:///{DEFAULT_DB_PATH}"
else:
    if raw_db_url.startswith("postgres://"):
        RESOLVED_DB_URL = raw_db_url.replace("postgres://", "postgresql://", 1)
    else:
        RESOLVED_DB_URL = raw_db_url


class Config:
    """Base application configuration."""
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    
    # Database
    DATABASE_URL = RESOLVED_DB_URL
    SQLALCHEMY_DATABASE_URI = RESOLVED_DB_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload settings
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 10 * 1024 * 1024))  # 10 MB
    UPLOAD_FOLDER = DEFAULT_UPLOAD_DIR if IS_VERCEL else (BASE_DIR / os.getenv("UPLOAD_FOLDER", "instance/uploads"))
    ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}
    
    # ElevenLabs Conversational AI
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
    ELEVENLABS_AGENT_ID = os.getenv("ELEVENLABS_AGENT_ID", "").strip()
    ELEVENLABS_AUTH_MODE = os.getenv("ELEVENLABS_AUTH_MODE", "signed_url").lower().strip()  # 'signed_url' or 'public'
    ELEVENLABS_ALLOWED_ORIGIN = os.getenv("ELEVENLABS_ALLOWED_ORIGIN", "").strip()
    ELEVENLABS_WEBHOOK_SECRET = os.getenv("ELEVENLABS_WEBHOOK_SECRET", "").strip()
    
    # LLM Settings
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower().strip()
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()
    LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip() or GEMINI_API_KEY
    
    # Auto-detect Gemini if key starts with AIza
    if LLM_API_KEY.startswith("AIza") and LLM_PROVIDER not in ("gemini", "mock"):
        LLM_PROVIDER = "gemini"

    # Default model depending on provider
    default_model = "gemini-3.8-flash" if LLM_PROVIDER == "gemini" else "gpt-4o-mini"
    LLM_MODEL = os.getenv("GEMINI_MODEL", "").strip() or os.getenv("LLM_MODEL", default_model).strip()
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip() or None

    @classmethod
    def is_elevenlabs_configured(cls) -> bool:
        if cls.ELEVENLABS_AUTH_MODE == "public":
            return bool(cls.ELEVENLABS_AGENT_ID)
        return bool(cls.ELEVENLABS_API_KEY and cls.ELEVENLABS_AGENT_ID)

    @classmethod
    def is_llm_configured(cls) -> bool:
        if cls.LLM_PROVIDER == "mock":
            return True
        key = cls.LLM_API_KEY or cls.GEMINI_API_KEY
        return bool(key and not key.startswith("your_"))


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    LLM_PROVIDER = "mock"
    ELEVENLABS_AGENT_ID = "mock-agent-id-123"
    ELEVENLABS_API_KEY = "mock-api-key-xyz"


class ProductionConfig(Config):
    DEBUG = False


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
