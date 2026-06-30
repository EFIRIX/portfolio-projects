from datetime import datetime, timezone
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_token_with_payload, decode_access_token
from app.db.session import get_db
from app.models.token_denylist import TokenDenylist
from app.models.user import User, UserRole
from app.services.consent import has_active_personal_data_consent


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    access_token: Optional[str] = Cookie(default=None, alias=settings.cookie_name),
) -> User:
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация")

    # Check if token is revoked
    payload = decode_token_with_payload(access_token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен")
    
    jti = payload.get("jti")
    if jti and db.query(TokenDenylist).filter(TokenDenylist.jti == jti).first():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Токен был отозван")

    user_id = decode_access_token(access_token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь временно отключён")
    if user.locked_until is not None:
        now = datetime.now(timezone.utc)
        locked_until = user.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until > now:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Аккаунт временно заблокирован")

    if settings.pd_consent_required and not has_active_personal_data_consent(db, user.id):
        allowed_paths = {
            f"{settings.api_v1_prefix}/auth/me",
            f"{settings.api_v1_prefix}/auth/logout",
            f"{settings.api_v1_prefix}/auth/refresh",
            f"{settings.api_v1_prefix}/auth/csrf-token",
            f"{settings.api_v1_prefix}/auth/consent/status",
            f"{settings.api_v1_prefix}/auth/consent/accept",
        }
        if request.url.path not in allowed_paths:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Нужно принять согласие на обработку персональных данных",
            )

    return user


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
    access_token: Optional[str] = Cookie(default=None, alias=settings.cookie_name),
) -> Optional[User]:
    if not access_token:
        return None
    try:
        return get_current_user(request=request, db=db, access_token=access_token)
    except HTTPException:
        return None


def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Раздел доступен только администратору")
    return current_user


def get_staff_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in {UserRole.curator, UserRole.methodist, UserRole.moderator, UserRole.admin}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Раздел доступен только сотрудникам")
    return current_user


def get_curator_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in {UserRole.curator, UserRole.admin}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Раздел доступен только кураторам")
    return current_user


def get_moderator_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in {UserRole.moderator, UserRole.admin}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Раздел доступен только модераторам")
    return current_user


def get_methodist_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in {UserRole.methodist, UserRole.admin}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Раздел доступен только методистам")
    return current_user


def get_parent_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.parent:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Раздел доступен только родителю")
    return current_user


def can_manage_dialog_status(user: User) -> bool:
    return user.role in {UserRole.curator, UserRole.methodist, UserRole.moderator, UserRole.admin}


def can_archive_dialog(user: User) -> bool:
    return user.role in {UserRole.methodist, UserRole.moderator, UserRole.admin}


def can_assign_deadlines(user: User) -> bool:
    return user.role in {UserRole.curator, UserRole.methodist, UserRole.moderator, UserRole.admin}


def can_view_all_students(user: User) -> bool:
    return user.role in {UserRole.methodist, UserRole.moderator, UserRole.admin}
