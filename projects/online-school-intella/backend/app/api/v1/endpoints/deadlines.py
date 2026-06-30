from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.api.deps import can_assign_deadlines, get_current_user
from app.db.session import get_db
from app.models.deadline import DeadlineCategory, DeadlineSource, DeadlineType, DeadlineUrgency, UserDeadline
from app.models.user import User, UserRole
from app.schemas.deadline import (
    DeadlineCancelRequest,
    DeadlineCreateRequest,
    DeadlineOut,
    DeadlinesSummaryOut,
    DeadlineUpdateRequest,
)
from app.services.deadlines import calc_urgency, sync_user_deadlines
from app.services.social import create_notification, create_notification_once_per_day

router = APIRouter(prefix="/deadlines", tags=["deadlines"])


def _serialize(item: UserDeadline) -> DeadlineOut:
    return DeadlineOut(
        id=item.id,
        title=item.title,
        description=item.description,
        item_type=item.item_type,
        item_ref=item.item_ref,
        due_at=item.due_at,
        urgency=item.urgency,
        source=item.source,
        category=item.category,
        status=_status_label(item),
        created_by_id=item.created_by_id,
        canceled_at=item.canceled_at,
        canceled_by_id=item.canceled_by_id,
        is_done=item.is_done,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _status_label(item: UserDeadline) -> str:
    if item.canceled_at is not None:
        return "completed"
    due_at = item.due_at if item.due_at.tzinfo else item.due_at.replace(tzinfo=timezone.utc)
    if item.is_done:
        return "completed"
    if due_at <= datetime.now(timezone.utc):
        return "overdue"
    if item.urgency in {DeadlineUrgency.soon, DeadlineUrgency.urgent}:
        return "soon"
    return "active"


@router.get("", response_model=list[DeadlineOut])
def list_deadlines(
    status_filter: str = Query(default="open", alias="status"),
    category: Optional[DeadlineCategory] = Query(default=None),
    urgency: Optional[DeadlineUrgency] = Query(default=None),
    user_id: Optional[int] = Query(default=None),
    from_date: Optional[datetime] = Query(default=None),
    to_date: Optional[datetime] = Query(default=None),
    sync: bool = Query(default=True),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_user_id = current_user.id
    if user_id is not None:
        if not can_assign_deadlines(current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для фильтрации по ученику")
        target_user = db.query(User).filter(User.id == user_id, User.role == UserRole.student).first()
        if not target_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ученик не найден")
        target_user_id = target_user.id

    if sync and target_user_id == current_user.id:
        sync_user_deadlines(db, current_user)
        db.commit()

    query = db.query(UserDeadline).filter(UserDeadline.user_id == target_user_id, UserDeadline.canceled_at.is_(None))
    if status_filter == "open":
        query = query.filter(UserDeadline.is_done.is_(False))
    elif status_filter == "done":
        query = query.filter(UserDeadline.is_done.is_(True))

    if urgency is not None:
        query = query.filter(UserDeadline.urgency == urgency)
    if category is not None:
        query = query.filter(UserDeadline.category == category)
    if from_date is not None:
        query = query.filter(UserDeadline.due_at >= from_date)
    if to_date is not None:
        query = query.filter(UserDeadline.due_at <= to_date)

    rows = (
        query.order_by(
            UserDeadline.is_done.asc(),
            UserDeadline.due_at.asc(),
            UserDeadline.id.asc(),
        )
        .limit(limit)
        .all()
    )
    return [_serialize(row) for row in rows]


@router.get("/upcoming", response_model=DeadlinesSummaryOut)
def upcoming_deadlines(
    days: int = Query(default=14, ge=1, le=60),
    limit: int = Query(default=8, ge=1, le=100),
    user_id: Optional[int] = Query(default=None),
    sync: bool = Query(default=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_user_id = current_user.id
    if user_id is not None:
        if not can_assign_deadlines(current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для фильтрации по ученику")
        target_user = db.query(User).filter(User.id == user_id, User.role == UserRole.student).first()
        if not target_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ученик не найден")
        target_user_id = target_user.id

    if sync and target_user_id == current_user.id:
        sync_user_deadlines(db, current_user)
        db.commit()

    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=days)

    rows = (
        db.query(UserDeadline)
        .filter(
            UserDeadline.user_id == target_user_id,
            UserDeadline.canceled_at.is_(None),
            UserDeadline.is_done.is_(False),
            and_(UserDeadline.due_at >= now - timedelta(days=1), UserDeadline.due_at <= horizon),
        )
        .order_by(UserDeadline.due_at.asc(), UserDeadline.id.asc())
        .limit(limit)
        .all()
    )
    urgent = sum(1 for row in rows if row.urgency == DeadlineUrgency.urgent)
    soon = sum(1 for row in rows if row.urgency == DeadlineUrgency.soon)

    if urgent > 0 and target_user_id == current_user.id:
        item = rows[0]
        created = create_notification_once_per_day(
            db=db,
            user_id=target_user_id,
            notification_type="deadline_reminder",
            title="Срочный дедлайн по подготовке",
            body=f"Сегодня важно закрыть задачу: {item.title}",
            href="/deadlines",
        )
        if created is not None:
            db.commit()

    return DeadlinesSummaryOut(
        total=len(rows),
        urgent=urgent,
        soon=soon,
        upcoming=[_serialize(row) for row in rows],
    )


@router.patch("/{deadline_id}", response_model=DeadlineOut)
def update_deadline(
    deadline_id: int,
    payload: DeadlineUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(UserDeadline).filter(UserDeadline.id == deadline_id)
    if current_user.role == UserRole.student:
        query = query.filter(UserDeadline.user_id == current_user.id)
    item = query.first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Дедлайн не найден")

    updates = payload.model_dump(exclude_unset=True)
    if current_user.role == UserRole.student:
        allowed_for_student = {"is_done"}
        if not set(updates.keys()).issubset(allowed_for_student):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ученик может только отмечать дедлайн выполненным")

    if "title" in updates and updates["title"] is not None:
        item.title = updates["title"].strip()
    if "description" in updates and updates["description"] is not None:
        item.description = updates["description"].strip()
    if "category" in updates and updates["category"] is not None:
        if not can_assign_deadlines(current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для смены категории дедлайна")
        item.category = updates["category"]
    if "due_at" in updates and updates["due_at"] is not None:
        if not can_assign_deadlines(current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для изменения дедлайна")
        due_at = updates["due_at"]
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=timezone.utc)
        item.due_at = due_at
        if "urgency" not in updates:
            item.urgency = calc_urgency(item.due_at)
    if "urgency" in updates and updates["urgency"] is not None:
        if not can_assign_deadlines(current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для изменения приоритета дедлайна")
        item.urgency = updates["urgency"]
    if "is_done" in updates and updates["is_done"] is not None:
        item.is_done = bool(updates["is_done"])
        if item.is_done and item.urgency != DeadlineUrgency.normal:
            item.urgency = DeadlineUrgency.normal

    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize(item)


@router.post("", response_model=DeadlineOut, status_code=status.HTTP_201_CREATED)
def create_deadline(
    payload: DeadlineCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not can_assign_deadlines(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только сотрудник может назначить дедлайн")

    target_user = db.query(User).filter(User.id == payload.user_id).first()
    if not target_user or target_user.role != UserRole.student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ученик не найден")

    item_ref = payload.item_ref.strip()
    if not item_ref:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите идентификатор цели дедлайна")

    if payload.item_type == DeadlineType.learning_response and not item_ref.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для дедлайна по ответу к куратору укажите числовой идентификатор ответа",
        )

    due_at = payload.due_at if payload.due_at.tzinfo else payload.due_at.replace(tzinfo=timezone.utc)
    deadline = UserDeadline(
        user_id=target_user.id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        item_type=payload.item_type,
        item_ref=item_ref,
        due_at=due_at,
        urgency=payload.urgency or calc_urgency(due_at),
        source=DeadlineSource.manual,
        category=payload.category,
        created_by_id=current_user.id,
    )
    db.add(deadline)
    db.commit()
    db.refresh(deadline)

    create_notification(
        db=db,
        user_id=deadline.user_id,
        notification_type="deadline_created",
        title="Назначен новый дедлайн",
        body=f"{deadline.title} ({_status_label(deadline)})",
        href="/deadlines",
    )
    db.commit()
    return _serialize(deadline)


@router.post("/{deadline_id}/cancel", response_model=DeadlineOut)
def cancel_deadline(
    deadline_id: int,
    payload: DeadlineCancelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not can_assign_deadlines(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только сотрудник может отменить дедлайн")
    item = db.query(UserDeadline).filter(UserDeadline.id == deadline_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Дедлайн не найден")

    item.canceled_at = datetime.now(timezone.utc)
    item.canceled_by_id = current_user.id
    if payload.reason:
        item.description = f"{item.description}\n\n[Отменён]: {payload.reason}".strip()
    db.add(item)
    create_notification(
        db=db,
        user_id=item.user_id,
        notification_type="deadline_canceled",
        title="Дедлайн отменён",
        body=item.title,
        href="/deadlines",
    )
    db.commit()
    db.refresh(item)
    return _serialize(item)
