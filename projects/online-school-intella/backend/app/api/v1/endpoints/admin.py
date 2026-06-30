from datetime import datetime, timedelta, timezone
import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.api.deps import get_admin_user, get_moderator_user
from app.core.config import settings
from app.core.security import get_password_hash, validate_password_strength
from app.db.session import get_db
from app.models.course import Course, CoursePurchase
from app.models.lesson import Lesson
from app.models.question import Question, QuestionDifficulty, QuestionType
from app.models.topic import Topic
from app.models.user import User, UserRole
from app.schemas.auth import CreateUserByStaffRequest, UpdateUserRoleRequest, UserOut, UserResetPasswordRequest
from app.schemas.course import CourseCreateRequest, CourseOut, CoursePurchaseWithCourseOut, CourseUpdateRequest
from app.schemas.question import QuestionCreateRequest, QuestionUpdateRequest, QuestionWithAnswerOut
from app.schemas.topic import (
    LessonCreateRequest,
    LessonOut,
    LessonUpdateRequest,
    TopicCreateRequest,
    TopicOut,
    TopicUpdateRequest,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _normalize_login(value: str) -> str:
    cleaned = value.strip().lower()
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"[^0-9a-zа-яё_-]", "", cleaned)
    cleaned = cleaned.strip("_")
    return cleaned[:64]


def _resolve_status_filter(status_filter: Optional[Literal["active", "locked", "disabled"]], query):
    now = datetime.now(timezone.utc)
    if status_filter == "active":
        query = query.filter(User.is_active.is_(True), or_(User.locked_until.is_(None), User.locked_until <= now))
    elif status_filter == "locked":
        query = query.filter(User.locked_until.is_not(None), User.locked_until > now)
    elif status_filter == "disabled":
        query = query.filter(User.is_active.is_(False))
    return query


def _serialize_course(course: Course, purchase: Optional[CoursePurchase] = None) -> CourseOut:
    access_status = "available"
    if purchase is not None:
        if purchase.status.value == "purchased":
            access_status = "purchased"
        elif purchase.status.value == "in_progress":
            access_status = "in_progress"
        elif purchase.status.value == "completed":
            access_status = "completed"

    return CourseOut(
        id=course.id,
        title=course.title,
        description=course.description,
        duration_weeks=course.duration_weeks,
        price_rub=course.price_rub,
        level=course.level,
        is_active=course.is_active,
        created_at=course.created_at,
        access_status=access_status,
    )


@router.get("/users", response_model=list[UserOut])
def list_users(
    role: Optional[UserRole] = Query(default=None),
    status_filter: Optional[Literal["active", "locked", "disabled"]] = Query(default=None, alias="status"),
    search: Optional[str] = Query(default=None, min_length=1),
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
    _=Depends(get_moderator_user),
):
    query = db.query(User)
    if role is not None:
        query = query.filter(User.role == role)
    query = _resolve_status_filter(status_filter, query)

    if search:
        term = search.strip().lower()
        query = query.filter(
            or_(
                func.lower(User.email).like(f"%{term}%"),
                func.lower(User.full_name).like(f"%{term}%"),
                func.lower(func.coalesce(User.nickname, "")).like(f"%{term}%"),
                func.lower(func.coalesce(User.login, "")).like(f"%{term}%"),
            )
        )
    return query.order_by(User.created_at.desc(), User.id.desc()).limit(limit).all()


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: CreateUserByStaffRequest,
    db: Session = Depends(get_db),
    current_staff: User = Depends(get_moderator_user),
):
    password_error = validate_password_strength(payload.password)
    if password_error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=password_error)

    target_role = payload.role
    if current_staff.role == UserRole.moderator and target_role in {UserRole.admin, UserRole.moderator}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Модератор не может создавать сотрудников этого уровня")

    normalized_email = payload.email.lower().strip()
    if db.query(User).filter(func.lower(User.email) == normalized_email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Адрес email уже зарегистрирован")

    normalized_login = _normalize_login(payload.login or normalized_email.split("@")[0])
    if len(normalized_login) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Логин должен содержать минимум 3 символа")
    if db.query(User).filter(func.lower(User.login) == normalized_login).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Логин уже занят")

    nickname = normalized_login
    suffix = 1
    while db.query(User).filter(func.lower(User.nickname) == nickname.lower()).first():
        nickname = f"{normalized_login[:56]}_{suffix}"
        suffix += 1

    user = User(
        email=normalized_email,
        login=normalized_login,
        full_name=payload.full_name.strip(),
        nickname=nickname,
        password_hash=get_password_hash(payload.password),
        role=target_role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}/role", response_model=UserOut)
def update_user_role(
    user_id: int,
    payload: UpdateUserRoleRequest,
    db: Session = Depends(get_db),
    current_staff: User = Depends(get_moderator_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    if current_staff.role == UserRole.moderator and payload.role in {UserRole.admin, UserRole.moderator}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для назначения этой роли")

    if user.role == UserRole.admin and payload.role != UserRole.admin:
        admin_count = db.query(User).filter(User.role == UserRole.admin).count()
        if admin_count <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="В системе должен оставаться хотя бы один администратор")
        if user.id == current_staff.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя снять роль администратора с текущего пользователя")

    user.role = payload.role
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}/lock", response_model=UserOut)
def lock_user(
    user_id: int,
    minutes: int = Query(default=settings.auth_lock_minutes, ge=1, le=60 * 24 * 30),
    db: Session = Depends(get_db),
    current_staff: User = Depends(get_moderator_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    if user.id == current_staff.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя заблокировать самого себя")
    if current_staff.role == UserRole.moderator and user.role in {UserRole.admin, UserRole.moderator}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для блокировки этого пользователя")

    user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    user.failed_login_attempts = 0
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}/unlock", response_model=UserOut)
def unlock_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_staff: User = Depends(get_moderator_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    if current_staff.role == UserRole.moderator and user.role in {UserRole.admin, UserRole.moderator}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для разблокировки этого пользователя")

    user.locked_until = None
    user.failed_login_attempts = 0
    user.is_active = True
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_staff: User = Depends(get_moderator_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    if user.id == current_staff.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя деактивировать самого себя")
    if current_staff.role == UserRole.moderator and user.role in {UserRole.admin, UserRole.moderator}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для деактивации этого пользователя")

    user.is_active = False
    user.locked_until = None
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}/activate", response_model=UserOut)
def activate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_staff: User = Depends(get_moderator_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    if current_staff.role == UserRole.moderator and user.role in {UserRole.admin, UserRole.moderator}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для активации этого пользователя")

    user.is_active = True
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/reset-password")
def admin_reset_password(
    user_id: int,
    payload: UserResetPasswordRequest,
    db: Session = Depends(get_db),
    current_staff: User = Depends(get_moderator_user),
):
    password_error = validate_password_strength(payload.new_password)
    if password_error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=password_error)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    if current_staff.role == UserRole.moderator and user.role in {UserRole.admin, UserRole.moderator}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для этого действия")

    user.password_hash = get_password_hash(payload.new_password)
    user.reset_token_version = int(user.reset_token_version) + 1
    user.failed_login_attempts = 0
    user.locked_until = None
    user.is_active = True
    db.add(user)
    db.commit()
    return {"message": "Пароль пользователя успешно сброшен"}


@router.get("/questions", response_model=list[QuestionWithAnswerOut])
def list_questions(
    topic_id: Optional[int] = Query(default=None),
    question_type: Optional[QuestionType] = Query(default=None, alias="type"),
    difficulty: Optional[QuestionDifficulty] = Query(default=None),
    section: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None, min_length=1),
    limit: int = Query(default=1000, ge=1, le=2000),
    db: Session = Depends(get_db),
    _=Depends(get_admin_user),
):
    query = db.query(Question)

    if topic_id is not None:
        query = query.filter(Question.topic_id == topic_id)
    if question_type is not None:
        query = query.filter(Question.type == question_type)
    if difficulty is not None:
        query = query.filter(Question.difficulty == difficulty)
    if section:
        query = query.join(Topic).filter(Topic.section == section)
    if search:
        query = query.filter(Question.text.ilike(f"%{search.strip()}%"))

    return query.order_by(Question.id.asc()).limit(limit).all()


@router.post("/topics", response_model=TopicOut)
def create_topic(payload: TopicCreateRequest, db: Session = Depends(get_db), _=Depends(get_admin_user)):
    topic = Topic(
        title=payload.title,
        description=payload.description,
        key_dates=payload.key_dates,
        theory_meta_json=payload.theory_meta_json.model_dump(),
        section=payload.section,
        section_order=payload.section_order,
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return topic


@router.put("/topics/{topic_id}", response_model=TopicOut)
def update_topic(
    topic_id: int,
    payload: TopicUpdateRequest,
    db: Session = Depends(get_db),
    _=Depends(get_admin_user),
):
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тема не найдена")

    updates = payload.model_dump(exclude_unset=True)
    if "theory_meta_json" in updates and updates["theory_meta_json"] is not None:
        updates["theory_meta_json"] = payload.theory_meta_json.model_dump()
    for field, value in updates.items():
        setattr(topic, field, value)

    db.commit()
    db.refresh(topic)
    return topic


@router.delete("/topics/{topic_id}")
def delete_topic(topic_id: int, db: Session = Depends(get_db), _=Depends(get_admin_user)):
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тема не найдена")

    db.delete(topic)
    db.commit()
    return {"message": "Тема удалена"}


@router.post("/lessons", response_model=LessonOut)
def create_lesson(payload: LessonCreateRequest, db: Session = Depends(get_db), _=Depends(get_admin_user)):
    topic = db.query(Topic).filter(Topic.id == payload.topic_id).first()
    if not topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тема не найдена")

    lesson = Lesson(**payload.model_dump())
    db.add(lesson)
    db.commit()
    db.refresh(lesson)
    return lesson


@router.put("/lessons/{lesson_id}", response_model=LessonOut)
def update_lesson(
    lesson_id: int,
    payload: LessonUpdateRequest,
    db: Session = Depends(get_db),
    _=Depends(get_admin_user),
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Урок не найден")

    updates = payload.model_dump(exclude_unset=True)
    if "topic_id" in updates:
        topic = db.query(Topic).filter(Topic.id == updates["topic_id"]).first()
        if not topic:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тема не найдена")

    for field, value in updates.items():
        setattr(lesson, field, value)

    db.commit()
    db.refresh(lesson)
    return lesson


@router.delete("/lessons/{lesson_id}")
def delete_lesson(lesson_id: int, db: Session = Depends(get_db), _=Depends(get_admin_user)):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Урок не найден")

    db.delete(lesson)
    db.commit()
    return {"message": "Урок удалён"}


@router.post("/questions", response_model=QuestionWithAnswerOut)
def create_question(payload: QuestionCreateRequest, db: Session = Depends(get_db), _=Depends(get_admin_user)):
    topic = db.query(Topic).filter(Topic.id == payload.topic_id).first()
    if not topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тема не найдена")

    if payload.correct_option >= len(payload.options):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Индекс правильного ответа выходит за границы options")

    question = Question(**payload.model_dump())
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@router.put("/questions/{question_id}", response_model=QuestionWithAnswerOut)
def update_question(
    question_id: int,
    payload: QuestionUpdateRequest,
    db: Session = Depends(get_db),
    _=Depends(get_admin_user),
):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Вопрос не найден")

    updates = payload.model_dump(exclude_unset=True)

    topic_id = updates.get("topic_id")
    if topic_id is not None and not db.query(Topic).filter(Topic.id == topic_id).first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тема не найдена")

    options = updates.get("options", question.options)
    correct_option = updates.get("correct_option", question.correct_option)
    if correct_option >= len(options):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Индекс правильного ответа выходит за границы options")

    for field, value in updates.items():
        setattr(question, field, value)

    db.commit()
    db.refresh(question)
    return question


@router.delete("/questions/{question_id}")
def delete_question(question_id: int, db: Session = Depends(get_db), _=Depends(get_admin_user)):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Вопрос не найден")

    db.delete(question)
    db.commit()
    return {"message": "Вопрос удалён"}


@router.get("/courses", response_model=list[CourseOut])
def admin_list_courses(
    search: Optional[str] = Query(default=None),
    include_inactive: bool = Query(default=True),
    db: Session = Depends(get_db),
    _=Depends(get_admin_user),
):
    query = db.query(Course)
    if not include_inactive:
        query = query.filter(Course.is_active.is_(True))
    if search:
        term = f"%{search.strip().lower()}%"
        query = query.filter(func.lower(Course.title).like(term))

    return [_serialize_course(course) for course in query.order_by(Course.created_at.desc(), Course.id.desc()).all()]


@router.post("/courses", response_model=CourseOut, status_code=status.HTTP_201_CREATED)
def admin_create_course(
    payload: CourseCreateRequest,
    db: Session = Depends(get_db),
    _=Depends(get_admin_user),
):
    existing = db.query(Course).filter(func.lower(Course.title) == payload.title.strip().lower()).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Курс с таким названием уже существует")

    course = Course(**payload.model_dump())
    db.add(course)
    db.commit()
    db.refresh(course)
    return _serialize_course(course)


@router.put("/courses/{course_id}", response_model=CourseOut)
def admin_update_course(
    course_id: int,
    payload: CourseUpdateRequest,
    db: Session = Depends(get_db),
    _=Depends(get_admin_user),
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Курс не найден")

    updates = payload.model_dump(exclude_unset=True)
    if "title" in updates:
        title = str(updates["title"]).strip().lower()
        conflict = db.query(Course).filter(func.lower(Course.title) == title, Course.id != course.id).first()
        if conflict:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Курс с таким названием уже существует")

    for field, value in updates.items():
        setattr(course, field, value)

    db.add(course)
    db.commit()
    db.refresh(course)
    return _serialize_course(course)


@router.delete("/courses/{course_id}")
def admin_delete_course(
    course_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_admin_user),
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Курс не найден")
    db.delete(course)
    db.commit()
    return {"message": "Курс удалён"}


@router.get("/purchases", response_model=list[CoursePurchaseWithCourseOut])
def admin_list_purchases(
    user_id: Optional[int] = Query(default=None),
    course_id: Optional[int] = Query(default=None),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _=Depends(get_admin_user),
):
    query = db.query(CoursePurchase).join(User, User.id == CoursePurchase.user_id).join(Course, Course.id == CoursePurchase.course_id)

    if user_id is not None:
        query = query.filter(CoursePurchase.user_id == user_id)
    if course_id is not None:
        query = query.filter(CoursePurchase.course_id == course_id)
    if search:
        term = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(User.email).like(term),
                func.lower(func.coalesce(User.nickname, "")).like(term),
                func.lower(Course.title).like(term),
            )
        )

    purchases = query.order_by(CoursePurchase.purchased_at.desc(), CoursePurchase.id.desc()).all()
    payload: list[CoursePurchaseWithCourseOut] = []
    for purchase in purchases:
        payload.append(
            CoursePurchaseWithCourseOut(
                id=purchase.id,
                user_id=purchase.user_id,
                course_id=purchase.course_id,
                status=purchase.status,
                purchased_at=purchase.purchased_at,
                updated_at=purchase.updated_at,
                course=_serialize_course(purchase.course, purchase=purchase),
            )
        )
    return payload
