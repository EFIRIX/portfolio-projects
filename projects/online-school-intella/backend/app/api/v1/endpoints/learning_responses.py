from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.file import File
from app.models.learning_response import (
    LearningResponse,
    LearningResponseReviewerRole,
    LearningResponseSourceType,
    LearningResponseStatus,
)
from app.models.support_chat import ChatStatus, CounterpartRole, MessageStatus, SupportChat, SupportMessage
from app.models.topic import Topic
from app.models.user import User, UserRole
from app.schemas.learning_response import (
    LearningResponseDraftUpdateRequest,
    LearningResponseOpenChatOut,
    LearningResponseOpenChatRequest,
    LearningResponseOut,
    LearningResponseReviewRequest,
    LearningResponseSubmitRequest,
    LearningResponseTriggerRequest,
)
from app.services.learning_response import (
    compute_rubric_total,
    create_or_get_learning_response,
    ensure_text_limit,
    validate_audio_file,
    validate_video_file,
)
from app.services.s3 import create_presigned_get_url
from app.services.social import create_notification, pick_default_staff

router = APIRouter(prefix="/learning-responses", tags=["learning-responses"])


def _is_staff(role: UserRole) -> bool:
    return role in {UserRole.curator, UserRole.methodist, UserRole.moderator, UserRole.admin}


def _parse_date(value: Optional[str], *, field_name: str) -> Optional[datetime]:
    if value is None:
        return None
    try:
        parsed = datetime.combine(date.fromisoformat(value), datetime.min.time(), tzinfo=timezone.utc)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Некорректная дата в параметре {field_name}") from exc
    return parsed


def _can_access_response(item: LearningResponse, current_user: User) -> bool:
    if current_user.role in {UserRole.admin, UserRole.moderator}:
        return True
    if current_user.role == UserRole.student:
        return item.student_id == current_user.id
    if current_user.role == UserRole.curator:
        return item.reviewer_id == current_user.id or item.reviewer_role in {None, LearningResponseReviewerRole.curator}
    if current_user.role == UserRole.methodist:
        return item.reviewer_id == current_user.id or item.reviewer_role in {None, LearningResponseReviewerRole.methodist}
    return False


def _serialize_file(file: Optional[File]) -> Optional[dict]:
    if not file:
        return None
    return {
        "id": file.id,
        "file_name": file.file_name,
        "mime_type": file.mime_type,
        "file_size": file.file_size,
        "download_url": create_presigned_get_url(file.storage_key, bucket_name="uploads") if file.storage_key else None,
    }


def _serialize_response(item: LearningResponse) -> LearningResponseOut:
    student = item.student
    reviewer = item.reviewer
    topic_title = item.topic.title if item.topic else None
    return LearningResponseOut(
        id=item.id,
        student_id=item.student_id,
        reviewer_id=item.reviewer_id,
        reviewer_role=item.reviewer_role,
        source_type=item.source_type,
        source_ref=item.source_ref,
        topic_id=item.topic_id,
        test_attempt_id=item.test_attempt_id,
        exam_attempt_id=item.exam_attempt_id,
        milestone_attempt_id=item.milestone_attempt_id,
        chat_id=item.chat_id,
        instruction=item.instruction,
        text_answer=item.text_answer,
        audio_file_id=item.audio_file_id,
        video_file_id=item.video_file_id,
        status=item.status,
        submitted_at=item.submitted_at,
        review_started_at=item.review_started_at,
        reviewed_at=item.reviewed_at,
        review_comment=item.review_comment,
        rubric_scores_json=item.rubric_scores_json or {},
        rubric_total=int(item.rubric_total or 0),
        credited=bool(item.credited),
        created_at=item.created_at,
        updated_at=item.updated_at,
        student_name=student.full_name if student else "Ученик",
        student_nickname=student.nickname if student else None,
        reviewer_name=reviewer.full_name if reviewer else None,
        reviewer_nickname=reviewer.nickname if reviewer else None,
        topic_title=topic_title,
        audio_file=_serialize_file(item.audio_file),
        video_file=_serialize_file(item.video_file),
    )


def _apply_draft_payload(
    db: Session,
    item: LearningResponse,
    *,
    payload: LearningResponseDraftUpdateRequest | LearningResponseSubmitRequest,
) -> None:
    updates = payload.model_dump(exclude_unset=True)

    if "text_answer" in updates:
        text_answer = updates.get("text_answer")
        ensure_text_limit(text_answer)
        normalized = text_answer.strip() if isinstance(text_answer, str) else None
        item.text_answer = normalized or None

    if "audio_file_id" in updates:
        audio_file_id = updates.get("audio_file_id")
        audio_file = validate_audio_file(db, audio_file_id, item.student_id) if audio_file_id is not None else None
        item.audio_file_id = audio_file.id if audio_file else None

    if "video_file_id" in updates:
        video_file_id = updates.get("video_file_id")
        video_file = validate_video_file(db, video_file_id, item.student_id) if video_file_id is not None else None
        item.video_file_id = video_file.id if video_file else None


def _ensure_payload_content(item: LearningResponse) -> None:
    has_text = bool((item.text_answer or "").strip())
    has_audio = item.audio_file_id is not None
    has_video = item.video_file_id is not None
    if not (has_text or has_audio or has_video):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Добавьте текст, аудио или видео перед отправкой на проверку",
        )


def _build_default_chat_message(item: LearningResponse) -> str:
    return (
        f"Ответ ученика #{item.id}: проверь, пожалуйста, вторую часть задания и дай комментарий. "
        f"Контекст: {item.source_type.value} ({item.source_ref})."
    )


@router.post("/trigger", response_model=LearningResponseOut, status_code=status.HTTP_201_CREATED)
def trigger_learning_response(
    payload: LearningResponseTriggerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == UserRole.student:
        student_id = current_user.id
    elif _is_staff(current_user.role):
        if not payload.student_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите student_id для создания задания сотрудником")
        student_id = payload.student_id
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для создания задания")

    student = db.query(User).filter(User.id == student_id, User.role == UserRole.student).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ученик не найден")

    if payload.topic_id is not None:
        topic_exists = db.query(Topic.id).filter(Topic.id == payload.topic_id).first()
        if not topic_exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тема не найдена")

    item = create_or_get_learning_response(
        db,
        student_id=student_id,
        source_type=payload.source_type,
        source_ref=payload.source_ref,
        topic_id=payload.topic_id,
        test_attempt_id=payload.test_attempt_id,
        exam_attempt_id=payload.exam_attempt_id,
        milestone_attempt_id=payload.milestone_attempt_id,
        reviewer_role=payload.reviewer_role,
        reviewer_id=payload.reviewer_id,
        instruction=payload.instruction,
    )
    db.commit()
    db.refresh(item)
    return _serialize_response(item)


@router.get("", response_model=list[LearningResponseOut])
def list_learning_responses(
    status_filter: Optional[LearningResponseStatus] = Query(default=None, alias="status"),
    source_type: Optional[LearningResponseSourceType] = Query(default=None),
    topic_id: Optional[int] = Query(default=None),
    student_id: Optional[int] = Query(default=None),
    reviewer_role: Optional[LearningResponseReviewerRole] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(LearningResponse)

    if current_user.role == UserRole.student:
        query = query.filter(LearningResponse.student_id == current_user.id)
    elif current_user.role == UserRole.curator:
        query = query.filter(
            or_(
                LearningResponse.reviewer_id == current_user.id,
                and_(
                    LearningResponse.reviewer_id.is_(None),
                    or_(
                        LearningResponse.reviewer_role.is_(None),
                        LearningResponse.reviewer_role == LearningResponseReviewerRole.curator,
                    ),
                ),
            )
        )
    elif current_user.role == UserRole.methodist:
        query = query.filter(
            or_(
                LearningResponse.reviewer_id == current_user.id,
                and_(
                    LearningResponse.reviewer_id.is_(None),
                    or_(
                        LearningResponse.reviewer_role.is_(None),
                        LearningResponse.reviewer_role == LearningResponseReviewerRole.methodist,
                    ),
                ),
            )
        )

    if status_filter is not None:
        query = query.filter(LearningResponse.status == status_filter)
    if source_type is not None:
        query = query.filter(LearningResponse.source_type == source_type)
    if topic_id is not None:
        query = query.filter(LearningResponse.topic_id == topic_id)
    if student_id is not None and current_user.role in {UserRole.admin, UserRole.moderator, UserRole.curator, UserRole.methodist}:
        query = query.filter(LearningResponse.student_id == student_id)
    if reviewer_role is not None:
        query = query.filter(LearningResponse.reviewer_role == reviewer_role)

    dt_from = _parse_date(date_from, field_name="date_from")
    dt_to = _parse_date(date_to, field_name="date_to")
    if dt_from is not None:
        query = query.filter(LearningResponse.created_at >= dt_from)
    if dt_to is not None:
        query = query.filter(LearningResponse.created_at <= dt_to.replace(hour=23, minute=59, second=59))

    items = query.order_by(LearningResponse.created_at.desc(), LearningResponse.id.desc()).limit(300).all()
    return [_serialize_response(item) for item in items]


@router.get("/{response_id}", response_model=LearningResponseOut)
def get_learning_response(
    response_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = db.query(LearningResponse).filter(LearningResponse.id == response_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ответ не найден")
    if not _can_access_response(item, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к ответу")
    return _serialize_response(item)


@router.patch("/{response_id}/draft", response_model=LearningResponseOut)
def save_learning_response_draft(
    response_id: int,
    payload: LearningResponseDraftUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = db.query(LearningResponse).filter(LearningResponse.id == response_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ответ не найден")
    if current_user.role != UserRole.student or item.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Черновик может редактировать только автор-ученик")
    if item.status not in {LearningResponseStatus.draft, LearningResponseStatus.needs_revision}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Черновик недоступен для редактирования в текущем статусе")

    _apply_draft_payload(db, item, payload=payload)
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize_response(item)


@router.post("/{response_id}/submit", response_model=LearningResponseOut)
def submit_learning_response(
    response_id: int,
    payload: Optional[LearningResponseSubmitRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = db.query(LearningResponse).filter(LearningResponse.id == response_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ответ не найден")
    if current_user.role != UserRole.student or item.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Отправить ответ может только автор-ученик")
    if item.status not in {LearningResponseStatus.draft, LearningResponseStatus.needs_revision}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ответ уже отправлен или проверен")

    if payload is not None:
        _apply_draft_payload(db, item, payload=payload)
    _ensure_payload_content(item)

    item.status = LearningResponseStatus.sent
    item.submitted_at = datetime.now(timezone.utc)
    item.review_started_at = None
    db.add(item)

    if item.reviewer_id:
        create_notification(
            db=db,
            user_id=item.reviewer_id,
            notification_type="response_submitted",
            title="Ученик отправил ответ на проверку",
            body="Открой задание и проверь письменную/устную часть.",
            href=f"/staff/reviews?id={item.id}",
        )

    db.commit()
    db.refresh(item)
    return _serialize_response(item)


@router.post("/{response_id}/take", response_model=LearningResponseOut)
def take_learning_response(
    response_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {UserRole.curator, UserRole.methodist, UserRole.moderator, UserRole.admin}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для проверки ответа")

    item = db.query(LearningResponse).filter(LearningResponse.id == response_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ответ не найден")
    if not _can_access_response(item, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к ответу")
    if item.status not in {LearningResponseStatus.sent, LearningResponseStatus.in_review}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Этот ответ нельзя взять в проверку")

    if current_user.role in {UserRole.curator, UserRole.methodist}:
        item.reviewer_id = current_user.id
        item.reviewer_role = (
            LearningResponseReviewerRole.methodist
            if current_user.role == UserRole.methodist
            else LearningResponseReviewerRole.curator
        )
    elif item.reviewer_id is None:
        item.reviewer_id = current_user.id

    item.status = LearningResponseStatus.in_review
    item.review_started_at = datetime.now(timezone.utc)
    db.add(item)

    create_notification(
        db=db,
        user_id=item.student_id,
        notification_type="response_in_review",
        title="Ответ принят на проверку",
        body="Куратор/методист уже просматривает твою работу.",
        href=f"/responses?id={item.id}",
    )
    db.commit()
    db.refresh(item)
    return _serialize_response(item)


@router.patch("/{response_id}/review", response_model=LearningResponseOut)
def review_learning_response(
    response_id: int,
    payload: LearningResponseReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {UserRole.curator, UserRole.methodist, UserRole.moderator, UserRole.admin}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для проверки ответа")

    item = db.query(LearningResponse).filter(LearningResponse.id == response_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ответ не найден")
    if not _can_access_response(item, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к ответу")
    if item.status not in {LearningResponseStatus.sent, LearningResponseStatus.in_review}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ответ нельзя проверить в текущем статусе")

    if current_user.role in {UserRole.curator, UserRole.methodist}:
        item.reviewer_id = current_user.id
        item.reviewer_role = (
            LearningResponseReviewerRole.methodist
            if current_user.role == UserRole.methodist
            else LearningResponseReviewerRole.curator
        )
    elif item.reviewer_id is None:
        item.reviewer_id = current_user.id

    rubric_scores = payload.rubric_scores.model_dump()
    rubric_total = compute_rubric_total(rubric_scores)

    item.status = (
        LearningResponseStatus.reviewed
        if payload.status == "reviewed"
        else LearningResponseStatus.needs_revision
    )
    item.review_started_at = item.review_started_at or datetime.now(timezone.utc)
    item.reviewed_at = datetime.now(timezone.utc)
    item.review_comment = (payload.review_comment or "").strip() or None
    item.rubric_scores_json = rubric_scores
    item.rubric_total = rubric_total
    item.credited = bool(payload.credited) if item.status == LearningResponseStatus.reviewed else False
    db.add(item)

    if item.status == LearningResponseStatus.needs_revision:
        create_notification(
            db=db,
            user_id=item.student_id,
            notification_type="response_revision_required",
            title="Нужна доработка ответа",
            body="Проверь комментарий специалиста и отправь обновлённый вариант.",
            href=f"/responses?id={item.id}",
        )
    else:
        create_notification(
            db=db,
            user_id=item.student_id,
            notification_type="response_feedback",
            title="Ответ проверен",
            body="Куратор/методист оставил комментарий по твоей работе.",
            href=f"/responses?id={item.id}",
        )
        if item.credited:
            create_notification(
                db=db,
                user_id=item.student_id,
                notification_type="response_credited",
                title="Ответ зачтён",
                body="Отлично! Вторая часть задания принята.",
                href=f"/responses?id={item.id}",
            )

    db.commit()
    db.refresh(item)
    return _serialize_response(item)


@router.post("/{response_id}/open-chat", response_model=LearningResponseOpenChatOut)
def open_chat_for_learning_response(
    response_id: int,
    payload: Optional[LearningResponseOpenChatRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = db.query(LearningResponse).filter(LearningResponse.id == response_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ответ не найден")
    if not _can_access_response(item, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к ответу")

    reviewer = item.reviewer
    if reviewer is None:
        role = item.reviewer_role or LearningResponseReviewerRole.curator
        staff = pick_default_staff(db, UserRole.methodist if role == LearningResponseReviewerRole.methodist else UserRole.curator)
        reviewer = staff
        if reviewer:
            item.reviewer_id = reviewer.id

    if reviewer is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Специалист пока недоступен")

    counterpart_role = CounterpartRole.methodist if reviewer.role == UserRole.methodist else CounterpartRole.curator

    chat = (
        db.query(SupportChat)
        .filter(
            SupportChat.student_id == item.student_id,
            SupportChat.curator_id == reviewer.id,
            SupportChat.counterpart_role == counterpart_role,
            SupportChat.topic_id == item.topic_id,
            SupportChat.status.in_([ChatStatus.open, ChatStatus.in_progress, ChatStatus.waiting_response]),
        )
        .order_by(SupportChat.updated_at.desc())
        .first()
    )
    if chat is None:
        chat = SupportChat(
            student_id=item.student_id,
            curator_id=reviewer.id,
            counterpart_role=counterpart_role,
            topic_id=item.topic_id,
            linked_attempt_id=item.test_attempt_id or item.exam_attempt_id or item.milestone_attempt_id,
            status=ChatStatus.open,
        )
        db.add(chat)
        db.flush()

    message_text = (payload.message.strip() if payload and payload.message else "") or _build_default_chat_message(item)
    sender_id = current_user.id
    message = SupportMessage(
        chat_id=chat.id,
        sender_id=sender_id,
        text=message_text,
        status=MessageStatus.sent,
        context_type="learning_response",
        context_ref=str(item.id),
    )
    db.add(message)

    item.chat_id = chat.id
    chat.updated_at = datetime.now(timezone.utc)
    db.add(chat)
    db.add(item)

    recipient_id = reviewer.id if sender_id == item.student_id else item.student_id
    create_notification(
        db=db,
        user_id=recipient_id,
        notification_type="new_message" if sender_id == item.student_id else "curator_reply",
        title="Новое сообщение по второй части задания",
        body=message_text[:140],
        href=f"/messages?chat={chat.id}",
    )

    db.commit()
    return LearningResponseOpenChatOut(chat_id=chat.id)
