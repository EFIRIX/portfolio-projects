import asyncio
from contextlib import asynccontextmanager, suppress
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.csrf import CSRFManager, get_csrf_token_from_header
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError, OperationalError
import logging

logger = logging.getLogger(__name__)
from app.models.progress import Progress
from app.models.user import User, UserRole
from app.services.learning_path import reconcile_learning_plans_nightly
from app.db.session import engine
from app.db.base import Base
import app.models  # noqa: F401


def _ensure_progress(db, user_id: int):
    existing_progress = db.query(Progress).filter(Progress.user_id == user_id).first()
    if existing_progress:
        return
    db.add(Progress(user_id=user_id, total_topics=0, mastered_topics=0, percent=0.0, weak_topics=[]))


def _unique_nickname(db, preferred: str) -> str:
    base = preferred.strip().lower() or "user"
    base = "".join(char if char.isalnum() else "_" for char in base).strip("_") or "user"
    nickname = base[:24]
    suffix = 1
    while db.query(User).filter(User.nickname == nickname).first():
        nickname = f"{base[:20]}_{suffix}"
        suffix += 1
    return nickname


def _unique_login(db, preferred: str) -> str:
    base = preferred.strip().lower() or "user"
    base = "".join(char if char.isalnum() else "_" for char in base).strip("_") or "user"
    login = base[:24]
    suffix = 1
    while db.query(User).filter(User.login == login).first():
        login = f"{base[:20]}_{suffix}"
        suffix += 1
    return login


def _ensure_staff_user(
    db,
    *,
    email: Optional[str],
    password: Optional[str],
    role: UserRole,
    full_name: str,
    fallback_nickname: str,
):
    if not email or not password:
        return

    normalized_email = email.lower().strip()
    if not normalized_email:
        return

    existing = db.query(User).filter(User.email == normalized_email).first()
    if existing:
        updates_required = False
        if existing.role != role:
            existing.role = role
            updates_required = True
        if not existing.nickname:
            existing.nickname = _unique_nickname(db, fallback_nickname)
            updates_required = True
        if not existing.login:
            existing.login = _unique_login(db, fallback_nickname)
            updates_required = True
        if updates_required:
            db.add(existing)
        _ensure_progress(db, existing.id)
        return

    user = User(
        email=normalized_email,
        login=_unique_login(db, fallback_nickname),
        nickname=_unique_nickname(db, fallback_nickname),
        full_name=full_name,
        password_hash=get_password_hash(password),
        role=role,
    )
    db.add(user)
    db.flush()
    _ensure_progress(db, user.id)


def ensure_core_users():
    db = SessionLocal()
    try:
        try:
            existing = db.query(User).filter(User.email == settings.first_admin_email.lower()).first()
        except (ProgrammingError, OperationalError):
            # DB schema not ready (tables not created yet). Skip creating core users.
            logger.info("Database schema not ready; skipping core user creation for now")
            return
        if existing:
            if not existing.nickname:
                existing.nickname = _unique_nickname(db, "admin")
                db.add(existing)
            if not existing.login:
                existing.login = _unique_login(db, "admin")
                db.add(existing)
        else:
            admin = User(
                email=settings.first_admin_email.lower(),
                login=_unique_login(db, "admin"),
                nickname=_unique_nickname(db, "admin"),
                full_name="Администратор",
                password_hash=get_password_hash(settings.first_admin_password),
                role=UserRole.admin,
            )
            db.add(admin)
            db.flush()
            _ensure_progress(db, admin.id)

        _ensure_staff_user(
            db,
            email=settings.first_curator_email,
            password=settings.first_curator_password,
            role=UserRole.curator,
            full_name="Куратор",
            fallback_nickname="curator",
        )
        _ensure_staff_user(
            db,
            email=settings.first_methodist_email,
            password=settings.first_methodist_password,
            role=UserRole.methodist,
            full_name="Методист",
            fallback_nickname="methodist",
        )
        _ensure_staff_user(
            db,
            email=settings.first_moderator_email,
            password=settings.first_moderator_password,
            role=UserRole.moderator,
            full_name="Модератор",
            fallback_nickname="moderator",
        )
        db.commit()
    finally:
        db.close()


def _sqlite_column_names(connection, table_name: str) -> set:
    rows = connection.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {str(row[1]) for row in rows}


def apply_sqlite_legacy_schema_patches() -> None:
    """Add missing columns for old local SQLite databases."""
    if engine.dialect.name != "sqlite":
        return

    patches = {
        "users": [
            ("login", "VARCHAR(64)"),
            ("nickname", "VARCHAR(64)"),
            ("accent_color", "VARCHAR(32) NOT NULL DEFAULT '#6366F1'"),
            ("avatar_frame", "VARCHAR(32) NOT NULL DEFAULT 'classic'"),
            ("profile_theme", "VARCHAR(32) NOT NULL DEFAULT 'clean'"),
            ("date_of_birth", "DATE"),
            ("onboarding_completed_at", "DATETIME"),
            ("reset_token_version", "INTEGER NOT NULL DEFAULT 0"),
            ("failed_login_attempts", "INTEGER NOT NULL DEFAULT 0"),
            ("locked_until", "DATETIME"),
            ("is_active", "BOOLEAN NOT NULL DEFAULT 1"),
        ],
        "support_chats": [
            ("counterpart_role", "VARCHAR(16) NOT NULL DEFAULT 'curator'"),
            ("subject", "VARCHAR(255)"),
            ("tags_json", "JSON NOT NULL DEFAULT '[]'"),
            ("close_reason", "VARCHAR(255)"),
            ("close_comment", "TEXT"),
            ("closed_at", "DATETIME"),
            ("closed_by_id", "INTEGER"),
        ],
        "support_questions": [
            ("assigned_role", "VARCHAR(16)"),
        ],
        "user_deadlines": [
            ("category", "VARCHAR(32) NOT NULL DEFAULT 'self_study'"),
            ("created_by_id", "INTEGER"),
            ("canceled_at", "DATETIME"),
            ("canceled_by_id", "INTEGER"),
        ],
        "test_attempts": [
            ("duration_seconds", "INTEGER NOT NULL DEFAULT 0"),
        ],
        "topics": [
            ("theory_meta_json", "JSON NOT NULL DEFAULT '{}'"),
        ],
        "oral_responses": [
            ("video_url", "VARCHAR(512)"),
        ],
    }

    with engine.begin() as conn:
        for table_name, columns in patches.items():
            existing_columns = _sqlite_column_names(conn, table_name)
            if not existing_columns:
                continue
            for column_name, column_def in columns:
                if column_name in existing_columns:
                    continue
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}"))
                logger.info("Patched legacy SQLite schema: %s.%s", table_name, column_name)


async def _learning_plan_reconcile_loop() -> None:
    interval_seconds = max(int(settings.learning_plan_reconcile_interval_hours), 1) * 3600
    while True:
        await asyncio.sleep(interval_seconds)
        db = SessionLocal()
        try:
            affected = reconcile_learning_plans_nightly(db)
            logger.info("Nightly learning plan reconcile completed: %s users", affected)
        except Exception:  # pragma: no cover - runtime safety net
            logger.exception("Nightly learning plan reconcile failed")
        finally:
            db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    apply_sqlite_legacy_schema_patches()
    ensure_core_users()
    reconcile_task: Optional[asyncio.Task] = None
    if settings.learning_plan_nightly_enabled:
        reconcile_task = asyncio.create_task(_learning_plan_reconcile_loop())
    try:
        yield
    finally:
        if reconcile_task is not None:
            reconcile_task.cancel()
            with suppress(asyncio.CancelledError):
                await reconcile_task


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)


def _error_payload(detail: str, status_code: int, code: str) -> dict:
    return {
        "detail": detail,  # backward-compatible field
        "error": {
            "code": code,
            "message": detail,
            "status_code": status_code,
        },
    }


@app.middleware("http")
async def csrf_protection_middleware(request: Request, call_next):
    if not settings.csrf_enabled:
        return await call_next(request)

    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return await call_next(request)

    if not request.url.path.startswith(settings.api_v1_prefix):
        return await call_next(request)

    if request.url.path in {
        f"{settings.api_v1_prefix}/auth/csrf-token",
        f"{settings.api_v1_prefix}/auth/csrf",
    }:
        return await call_next(request)

    cookie_token = request.cookies.get(settings.csrf_cookie_name) or ""
    header_token = get_csrf_token_from_header(request.headers) or ""
    if not CSRFManager.validate_token(cookie_token, header_token):
        logger.warning(
            "CSRF validation failed for %s %s from %s",
            request.method,
            request.url.path,
            request.client.host if request.client else "unknown",
        )
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=_error_payload(
                "CSRF-токен отсутствует или недействителен",
                status.HTTP_403_FORBIDDEN,
                "csrf_validation_failed",
            ),
        )

    return await call_next(request)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else "Ошибка запроса"
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(detail, exc.status_code, "http_error"),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Convert Pydantic validation errors to readable format"""
    errors = exc.errors()
    if errors:
        first_error = errors[0]
        error_type = first_error.get("type", "validation_error")
        msg = first_error.get("msg", "Ошибка валидации")
        
        # Handle field-level errors
        loc = first_error.get("loc", [])
        if loc and loc[0] != "body":
            field_name = str(loc[-1])
            # Human-readable field names
            field_map = {
                "identifier": "Email или логин",
                "email": "Email",
                "password": "Пароль",
                "full_name": "Полное имя",
                "login": "Логин"
            }
            display_name = field_map.get(field_name, field_name)
            
            # Translate common error messages
            if error_type == "missing":
                detail = f"Поле '{display_name}' обязательно"
            elif error_type == "string_too_short":
                detail = f"Поле '{display_name}': минимум 8 символов"
            elif "at least" in msg:
                detail = f"Поле '{display_name}': минимум 8 символов"
            elif error_type == "string_type":
                detail = f"Поле '{display_name}' должно быть строкой"
            else:
                detail = f"Поле '{display_name}': {msg}"
        else:
            detail = msg
    else:
        detail = "Ошибка валидации данных"
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_error_payload(detail, status.HTTP_422_UNPROCESSABLE_ENTITY, "validation_error"),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_payload("Внутренняя ошибка сервера", status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error"),
    )


app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health")
def health_check():
    return {"status": "ok"}
