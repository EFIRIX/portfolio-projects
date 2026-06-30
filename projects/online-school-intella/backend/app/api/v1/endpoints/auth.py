"""Authentication endpoints with production-ready security"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.csrf import CSRFManager
from app.core.rate_limit import (
    check_rate_limit,
    login_limiter,
    register_rate_limit_failure,
    reset_rate_limit,
)
from app.core.security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_password_reset_token,
    decode_refresh_token,
    decode_token_with_payload,
    get_password_hash,
    validate_password_strength,
    verify_password,
)
from app.db.session import get_db
from app.models.progress import Progress
from app.models.token_denylist import TokenDenylist
from app.models.user import User, UserRole
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    ConsentAcceptRequest,
    ConsentStatusResponse,
    CSRFTokenResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LogoutResponse,
    RefreshTokenResponse,
    RegisterRequest,
    ResetPasswordRequest,
    UserOut,
)
from app.services.consent import get_personal_data_consent, has_active_personal_data_consent, record_personal_data_consent
from app.services.token_service import revoke_token

router = APIRouter(prefix="/auth", tags=["auth"])

AUTH_NO_STORE_HEADER = "no-store, no-cache, must-revalidate, private"


def _set_no_store_headers(response: Response) -> None:
    response.headers["Cache-Control"] = AUTH_NO_STORE_HEADER
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"


def _normalize_login(value: str) -> str:
    cleaned = value.strip().lower()
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"[^0-9a-zа-яё_-]", "", cleaned)
    cleaned = cleaned.strip("_")
    return cleaned[:64]


def _build_unique_nickname(db: Session, raw_base: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "_" for char in raw_base).strip("_")
    base = cleaned[:24] or "student"
    nickname = base
    suffix = 1
    while db.query(User).filter(func.lower(User.nickname) == nickname.lower()).first():
        nickname = f"{base[:20]}_{suffix}"
        suffix += 1
    return nickname


def _login_conflict(db: Session, login: str, user_id: Optional[int] = None) -> bool:
    query = db.query(User).filter(func.lower(User.login) == login.lower())
    if user_id is not None:
        query = query.filter(User.id != user_id)
    return query.first() is not None


def _password_policy_or_400(password: str):
    message = validate_password_strength(password)
    if message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def _auth_identifier(payload: LoginRequest) -> str:
    identifier = (payload.identifier or payload.email or "").strip().lower()
    if not identifier:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите email или логин для входа")
    return identifier


def _request_ip(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _is_disposable_email(email: str) -> bool:
    try:
        domain = email.rsplit("@", 1)[1].strip().lower()
    except IndexError:
        return False
    return domain in set(settings.disposable_email_domains_list)


def _set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    csrf_token: str
) -> None:
    """Set secure auth cookies"""
    response.set_cookie(
        key=settings.cookie_name,
        value=access_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.refresh_token_expire_days * 86400,
        path="/api/v1/auth",  # More restrictive path
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        httponly=False,  # Must be readable from JavaScript for CSRF protection
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.refresh_token_expire_days * 86400,
        path="/",
    )


@router.get("/csrf-token", response_model=CSRFTokenResponse)
def get_csrf_token(response: Response) -> CSRFTokenResponse:
    """Get CSRF token (must be called before POST requests)"""
    csrf_token = CSRFManager.generate_token()
    _set_no_store_headers(response)
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=3600,
        path="/",
    )
    return CSRFTokenResponse(csrf_token=csrf_token)


@router.get("/csrf", response_model=CSRFTokenResponse)
def get_csrf_token_alias(response: Response) -> CSRFTokenResponse:
    """Backward-compatible alias for CSRF bootstrap endpoint."""
    return get_csrf_token(response)


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
):
    """Register new user with auth tokens"""
    if not payload.accept_personal_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для регистрации нужно согласиться на обработку персональных данных",
        )

    _password_policy_or_400(payload.password)

    email = payload.email.lower().strip()
    if _is_disposable_email(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Используй постоянный email-адрес. Временные почтовые домены не поддерживаются.",
        )

    existing = db.query(User).filter(func.lower(User.email) == email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Адрес email уже зарегистрирован")

    if payload.login:
        normalized_login = _normalize_login(payload.login)
        if len(normalized_login) < 3:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Логин должен содержать минимум 3 символа")
        if _login_conflict(db, normalized_login):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Логин уже занят")
    else:
        normalized_login = _normalize_login(payload.email.split("@")[0])
        if normalized_login and _login_conflict(db, normalized_login):
            normalized_login = f"{normalized_login}_{int(datetime.now(timezone.utc).timestamp()) % 100000}"

    target_role = payload.role or UserRole.student
    if target_role not in {UserRole.student, UserRole.parent}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Самостоятельная регистрация доступна только для ученика или родителя",
        )

    user = User(
        email=email,
        login=normalized_login or None,
        nickname=_build_unique_nickname(db, payload.email.split("@")[0]),
        full_name=payload.full_name,
        date_of_birth=payload.date_of_birth,
        password_hash=get_password_hash(payload.password),
        role=target_role,
    )
    db.add(user)
    db.flush()

    if user.role == UserRole.student:
        db.add(Progress(user_id=user.id, total_topics=0, mastered_topics=0, percent=0, weak_topics=[]))
    record_personal_data_consent(
        db,
        user_id=user.id,
        ip_address=_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Пользователь с такими данными уже существует")
    db.refresh(user)

    # Generate tokens
    access_token = create_access_token(str(user.id), timedelta(minutes=settings.access_token_expire_minutes))
    refresh_token = create_refresh_token(str(user.id), timedelta(days=settings.refresh_token_expire_days))
    csrf_token = CSRFManager.generate_token()

    # Set cookies
    _set_no_store_headers(response)
    _set_auth_cookies(response, access_token, refresh_token, csrf_token)

    return AuthResponse(message="Регистрация прошла успешно", user=UserOut.model_validate(user))


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
):
    """Login user with rate limiting and anti-brute-force"""
    identifier = _auth_identifier(payload)
    limiter_key = f"{_request_ip(request).lower()}:{identifier.lower()}"

    user = db.query(User).filter(
        or_(func.lower(User.email) == identifier, func.lower(func.coalesce(User.login, "")) == identifier)
    ).first()

    # Return account lock information before rate-limit response.
    now = datetime.now(timezone.utc)
    if user and user.locked_until is not None:
        locked_until = user.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until > now:
            minutes = max(int((locked_until - now).total_seconds() // 60), 1)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Слишком много неудачных попыток. Повторите через {minutes} мин.",
            )

    # Rate limiting by IP + identifier.
    if not check_rate_limit(limiter_key, login_limiter):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много попыток входа. Попробуйте позже.",
        )

    if not user:
        register_rate_limit_failure(limiter_key, login_limiter)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин/email или пароль")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь деактивирован")

    if not verify_password(payload.password, user.password_hash):
        register_rate_limit_failure(limiter_key, login_limiter)
        user.failed_login_attempts = int(user.failed_login_attempts) + 1
        if user.failed_login_attempts >= settings.auth_max_failed_logins:
            user.locked_until = now + timedelta(minutes=settings.auth_lock_minutes)
            user.failed_login_attempts = 0
            reset_rate_limit(limiter_key, login_limiter)
        db.add(user)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин/email или пароль")

    user.failed_login_attempts = 0
    user.locked_until = None
    db.add(user)
    db.commit()
    db.refresh(user)
    reset_rate_limit(limiter_key, login_limiter)

    # Generate tokens
    access_token = create_access_token(str(user.id), timedelta(minutes=settings.access_token_expire_minutes))
    refresh_token = create_refresh_token(str(user.id), timedelta(days=settings.refresh_token_expire_days))
    csrf_token = CSRFManager.generate_token()

    # Set cookies
    _set_no_store_headers(response)
    _set_auth_cookies(response, access_token, refresh_token, csrf_token)

    return AuthResponse(message="Вход выполнен", user=UserOut.model_validate(user))


@router.post("/refresh", response_model=RefreshTokenResponse)
def refresh_access_token(
    response: Response,
    db: Session = Depends(get_db),
    refresh_token: Optional[str] = Cookie(default=None, alias=settings.refresh_cookie_name),
):
    """Refresh access token using refresh token (silent refresh)"""
    _set_no_store_headers(response)
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется refresh token")

    payload = decode_token_with_payload(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный refresh token")

    decoded = decode_refresh_token(refresh_token)
    if not decoded:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный refresh token")
    user_id, jti = decoded

    # Check if token is revoked
    if db.query(TokenDenylist).filter(TokenDenylist.jti == jti).first():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token был отозван")

    # Verify user still exists and active
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден или неактивен")

    # Revoke old refresh token before issuing a new one (rotation).
    expires_at_ts = payload.get("exp")
    if not isinstance(expires_at_ts, (int, float)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный refresh token")
    revoke_token(
        db,
        jti,
        int(user_id),
        "refresh",
        datetime.fromtimestamp(expires_at_ts, tz=timezone.utc),
    )

    # Generate new token pair.
    new_access_token = create_access_token(str(user.id), timedelta(minutes=settings.access_token_expire_minutes))
    new_refresh_token = create_refresh_token(str(user.id), timedelta(days=settings.refresh_token_expire_days))

    # Set new access and refresh tokens
    response.set_cookie(
        key=settings.cookie_name,
        value=new_access_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=new_refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.refresh_token_expire_days * 86400,
        path="/api/v1/auth",
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=CSRFManager.generate_token(),
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.refresh_token_expire_days * 86400,
        path="/",
    )

    return RefreshTokenResponse(
        message="Токен обновлён",
        access_token=new_access_token if settings.app_env.lower() == "development" else None,
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(
    response: Response,
    db: Session = Depends(get_db),
    access_token: Optional[str] = Cookie(default=None, alias=settings.cookie_name),
    refresh_token: Optional[str] = Cookie(default=None, alias=settings.refresh_cookie_name),
):
    """Logout user (revoke tokens and clear cookies)"""
    _set_no_store_headers(response)
    # Revoke access token.
    if access_token:
        payload = decode_token_with_payload(access_token)
        if payload and payload.get("sub"):
            user_id = int(payload["sub"])
            jti = payload.get("jti")
            exp = datetime.fromtimestamp(payload.get("exp", 0), tz=timezone.utc)
            if jti:
                if not db.query(TokenDenylist).filter(TokenDenylist.jti == jti).first():
                    revoke_token(db, jti, user_id, "access", exp)

    # Revoke refresh token.
    if refresh_token:
        payload = decode_token_with_payload(refresh_token)
        if payload and payload.get("sub"):
            user_id = int(payload["sub"])
            jti = payload.get("jti")
            exp = datetime.fromtimestamp(payload.get("exp", 0), tz=timezone.utc)
            if jti:
                if not db.query(TokenDenylist).filter(TokenDenylist.jti == jti).first():
                    revoke_token(db, jti, user_id, "refresh", exp)

    # Clear cookies
    response.delete_cookie(key=settings.cookie_name, path="/")
    response.delete_cookie(key=settings.refresh_cookie_name, path="/api/v1/auth")
    response.delete_cookie(key=settings.csrf_cookie_name, path="/")

    return LogoutResponse(message="Вы вышли из аккаунта")


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    """Get current user info"""
    return current_user


@router.get("/consent/status", response_model=ConsentStatusResponse)
def get_consent_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    accepted = has_active_personal_data_consent(db, current_user.id)
    latest = get_personal_data_consent(db, current_user.id, document_version=settings.pd_consent_version)
    return ConsentStatusResponse(
        required=settings.pd_consent_required,
        accepted=accepted,
        document_version=settings.pd_consent_version,
        accepted_at=latest.accepted_at if latest else None,
    )


@router.post("/consent/accept", response_model=ConsentStatusResponse)
def accept_personal_data_consent(
    payload: ConsentAcceptRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not payload.accept:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Для продолжения нужно подтвердить согласие")
    consent = record_personal_data_consent(
        db,
        user_id=current_user.id,
        ip_address=_request_ip(request),
        user_agent=request.headers.get("user-agent"),
        document_version=settings.pd_consent_version,
    )
    db.commit()
    return ConsentStatusResponse(
        required=settings.pd_consent_required,
        accepted=True,
        document_version=consent.document_version,
        accepted_at=consent.accepted_at,
    )


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change user password"""
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Новый пароль должен отличаться от текущего")

    _password_policy_or_400(payload.new_password)

    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Текущий пароль введён неверно")

    current_user.password_hash = get_password_hash(payload.new_password)
    current_user.reset_token_version = int(current_user.reset_token_version) + 1
    db.add(current_user)
    db.commit()
    
    return {"message": "Пароль успешно изменён"}


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(func.lower(User.email) == payload.email.lower()).first()
    if not user:
        return ForgotPasswordResponse(message="Если email существует, инструкция по сбросу уже готова")

    reset_token = create_password_reset_token(
        user_id=str(user.id),
        reset_token_version=int(user.reset_token_version),
    )
    if settings.app_env.lower() == "development":
        return ForgotPasswordResponse(
            message="Если email существует, инструкция по сбросу уже готова",
            reset_token=reset_token,
        )
    return ForgotPasswordResponse(message="Если email существует, инструкция по сбросу уже готова")


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Reset password with token"""
    _password_policy_or_400(payload.new_password)

    decoded_payload = decode_password_reset_token(payload.token)
    if not decoded_payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недействительный или просроченный токен сброса")

    user_id, token_version = decoded_payload
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недействительный или просроченный токен сброса")

    if int(user.reset_token_version) != int(token_version):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недействительный или просроченный токен сброса")

    user.password_hash = get_password_hash(payload.new_password)
    user.reset_token_version = int(user.reset_token_version) + 1
    user.failed_login_attempts = 0
    user.locked_until = None
    db.add(user)
    db.commit()

    return {"message": "Пароль успешно обновлён"}
