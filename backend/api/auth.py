from collections import defaultdict
from datetime import datetime, timedelta
import time
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from core.config import (
    ALLOW_REGISTRATION,
    AUTH_RATE_LIMIT_PER_MINUTE,
    COOKIE_SECURE,
    INITIAL_ADMIN_EMAIL,
    INITIAL_ADMIN_NAME,
    INITIAL_ADMIN_PASSWORD,
    SECRET_KEY,
)
from core.database import SessionLocal, get_db
from core.database_models import User
from core.dependencies import get_current_user
from core.logger import get_logger
from models.schemas import AdminCreateUserRequest, LoginRequest, RegisterRequest

router = APIRouter()
logger = get_logger(__name__)
password_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
SESSION_SECONDS = 24 * 60 * 60

_rate_lock = Lock()
_auth_attempts: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(request: Request, action: str) -> None:
    client_ip = request.client.host if request.client else "unknown"
    key = f"{action}:{client_ip}"
    now = time.monotonic()
    cutoff = now - 60.0
    with _rate_lock:
        recent = [t for t in _auth_attempts[key] if t > cutoff]
        if len(recent) >= AUTH_RATE_LIMIT_PER_MINUTE:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many authentication attempts. Please wait a minute and try again.",
            )
        recent.append(now)
        _auth_attempts[key] = recent


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "profile_picture": user.profile_picture,
        "is_admin": user.is_admin,
        "optimization_objective": user.optimization_objective or "revenue",
    }


def _set_session(response: Response, user: User) -> None:
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY must be configured")
    token = jwt.encode(
        {
            "sub": str(user.id),
            "email": user.email,
            "admin": user.is_admin,
            "exp": datetime.utcnow() + timedelta(seconds=SESSION_SECONDS),
        },
        SECRET_KEY,
        algorithm="HS256",
    )
    response.set_cookie(
        key="auth_token",
        value=token,
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="none" if COOKIE_SECURE else "lax",
    )


def bootstrap_admin() -> None:
    """Create the first administrator once, using deployment-only environment variables."""
    if not INITIAL_ADMIN_EMAIL or not INITIAL_ADMIN_PASSWORD:
        return
    if len(INITIAL_ADMIN_PASSWORD) < 12:
        raise RuntimeError("INITIAL_ADMIN_PASSWORD must contain at least 12 characters")
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == INITIAL_ADMIN_EMAIL).first():
            return
        db.add(
            User(
                email=INITIAL_ADMIN_EMAIL,
                name=INITIAL_ADMIN_NAME,
                hashed_password=password_context.hash(INITIAL_ADMIN_PASSWORD),
                auth_provider="local",
                is_admin=True,
            )
        )
        db.commit()
        logger.info("Initial administrator account created")
    finally:
        db.close()


@router.get("/setup-status")
def setup_status():
    return {"registration_enabled": ALLOW_REGISTRATION}


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    _check_rate_limit(request, "register")
    if not ALLOW_REGISTRATION:
        raise HTTPException(
            status_code=403,
            detail="Account registration is disabled. Ask an administrator for access.",
        )
    email = str(payload.email).lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="An account already exists for this email address.")
    user = User(
        email=email,
        name=payload.name.strip(),
        hashed_password=password_context.hash(payload.password),
        auth_provider="local",
        is_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _set_session(response, user)
    return _user_payload(user)


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    _check_rate_limit(request, "login")
    email = str(payload.email).lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.hashed_password or not password_context.verify(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    _set_session(response, user)
    return _user_payload(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie("auth_token", secure=COOKIE_SECURE, samesite="none" if COOKIE_SECURE else "lax")


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return _user_payload(current_user)


@router.get("/users")
def list_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required")
    return [_user_payload(u) for u in db.query(User).order_by(User.id.asc()).all()]


@router.post("/users", status_code=status.HTTP_201_CREATED)
def admin_create_user(
    payload: AdminCreateUserRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required")
    email = str(payload.email).lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="An account already exists for this email address.")
    user = User(
        email=email,
        name=payload.name.strip(),
        hashed_password=password_context.hash(payload.password),
        auth_provider="local",
        is_admin=payload.is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_payload(user)
