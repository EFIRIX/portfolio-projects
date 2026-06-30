from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import case
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.deadline import UserDeadline
from app.models.course import Course, CoursePurchase
from app.models.diagnostic_result import DiagnosticResult
from app.models.exam_attempt import ExamAttempt
from app.models.test_attempt import TestAttempt
from app.models.topic import Topic
from app.models.user import User
from app.schemas.progress import DashboardOut, HistoryItem
from app.services.deadlines import sync_user_deadlines
from app.services.learning_path import build_learning_plan_response, ensure_learning_plan
from app.services.progress import recalculate_progress, topic_strength_groups
from app.services.recommendation import build_next_step
from app.services.social import create_notification_once_per_day

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def calculate_streak(activity_days: set) -> int:
    if not activity_days:
        return 0

    streak = 0
    cursor = datetime.now(timezone.utc).date()
    while cursor in activity_days:
        streak += 1
        cursor = cursor - timedelta(days=1)
    return streak


def _ordered_topics(db: Session) -> list[Topic]:
    return (
        db.query(Topic)
        .order_by(
            case((Topic.section_order.is_(None), 1), else_=0).asc(),
            Topic.section_order.asc(),
            Topic.id.asc(),
        )
        .all()
    )


def _latest_scores_by_topic(test_attempts: list[TestAttempt]) -> dict[int, float]:
    latest_scores: dict[int, float] = {}
    for attempt in test_attempts:
        if attempt.topic_id not in latest_scores:
            latest_scores[attempt.topic_id] = float(attempt.score_percent)
    return latest_scores


def _latest_mistake_topic_id(test_attempts: list[TestAttempt]) -> Optional[int]:
    for attempt in test_attempts:
        wrong_in_attempt: dict[int, int] = {}
        for detail in attempt.details or []:
            topic_id = detail.get("topic_id")
            if not isinstance(topic_id, int):
                continue
            if bool(detail.get("is_correct")):
                continue
            wrong_in_attempt[topic_id] = wrong_in_attempt.get(topic_id, 0) + 1
        if wrong_in_attempt:
            return max(wrong_in_attempt.items(), key=lambda item: item[1])[0]
    return None


def _build_daily_plan(
    topics: list[Topic],
    weak_topics: list[Topic],
    latest_scores: dict[int, float],
    mistake_topic_id: Optional[int],
) -> list[dict]:
    tasks: list[dict] = []

    def add_task(kind: str, title: str, description: str, href: str, action_label: str, priority: int):
        if len(tasks) >= 4:
            return
        if any(task["kind"] == kind and task["href"] == href for task in tasks):
            return
        tasks.append(
            {
                "kind": kind,
                "title": title,
                "description": description,
                "href": href,
                "action_label": action_label,
                "priority": priority,
            }
        )

    if weak_topics:
        weak_topic = weak_topics[0]
        add_task(
            kind="weak_topic",
            title=f"Повтори слабую тему: {weak_topic.title}",
            description="Подними результат в слабой теме, чтобы закрепить базу.",
            href=f"/topics/{weak_topic.id}",
            action_label="Повторить тему",
            priority=1,
        )
        add_task(
            kind="weak_topic_test",
            title=f"Проверь прогресс: тест по теме {weak_topic.title}",
            description="Сразу после повторения закрепи результат коротким тестом.",
            href=f"/topics/{weak_topic.id}/test",
            action_label="Пройти тест",
            priority=1,
        )

    if mistake_topic_id is not None:
        add_task(
            kind="mistakes",
            title="Потренируй ошибки прошлых попыток",
            description="Быстрый режим на вопросах, где раньше были ошибки.",
            href=f"/topics/{mistake_topic_id}/mistakes",
            action_label="Повторить ошибки",
            priority=1,
        )

    new_topic = next((topic for topic in topics if topic.id not in latest_scores), None)
    if new_topic:
        add_task(
            kind="new_topic",
            title=f"Пройди новую тему: {new_topic.title}",
            description="Это ближайшая неосвоенная тема в твоей траектории.",
            href=f"/topics/{new_topic.id}",
            action_label="Изучить тему",
            priority=2,
        )
        add_task(
            kind="new_topic_test",
            title=f"Закрепи тему: тест {new_topic.title}",
            description="После изучения сразу проверь понимание ключевых дат и связей.",
            href=f"/topics/{new_topic.id}/test",
            action_label="Пройти тест",
            priority=2,
        )

    add_task(
        kind="exam",
        title="Сделай пробный экзамен",
        description="Проверь общий уровень готовности в формате реального экзамена.",
        href="/exam",
        action_label="Начать пробник",
        priority=3,
    )

    if len(tasks) < 3 and topics:
        fallback_topic = topics[0]
        add_task(
            kind="fallback_topic",
            title=f"Поддержи ритм: тема {fallback_topic.title}",
            description="Даже короткая сессия помогает сохранить прогресс и streak.",
            href=f"/topics/{fallback_topic.id}",
            action_label="Продолжить обучение",
            priority=3,
        )

    tasks.sort(key=lambda task: (task["priority"], task["title"]))
    return tasks[:4]


@router.get("", response_model=DashboardOut)
def get_dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    progress = recalculate_progress(db, current_user.id)
    sync_user_deadlines(db, current_user, weak_topic_ids=progress.weak_topics)
    db.commit()

    test_attempts = (
        db.query(TestAttempt)
        .filter(TestAttempt.user_id == current_user.id)
        .order_by(TestAttempt.created_at.desc())
        .limit(10)
        .all()
    )
    exam_attempts = (
        db.query(ExamAttempt)
        .filter(ExamAttempt.user_id == current_user.id)
        .order_by(ExamAttempt.created_at.desc())
        .limit(10)
        .all()
    )
    diagnostic_attempts = (
        db.query(DiagnosticResult)
        .filter(DiagnosticResult.user_id == current_user.id)
        .order_by(DiagnosticResult.created_at.desc())
        .limit(10)
        .all()
    )

    latest_exam_result = exam_attempts[0].score_percent if exam_attempts else None
    topics = _ordered_topics(db)

    weak_topics = (
        db.query(Topic).filter(Topic.id.in_(progress.weak_topics)).all()
        if progress.weak_topics
        else []
    )
    strong_topics, review_topics = topic_strength_groups(
        topics=topics,
        test_attempts=test_attempts,
        weak_topic_ids=set(progress.weak_topics or []),
    )

    activity_days = {
        attempt.created_at.date() for attempt in test_attempts + exam_attempts + diagnostic_attempts
    }
    streak_days = calculate_streak(activity_days)
    latest_activity = max(
        [attempt.created_at for attempt in test_attempts + exam_attempts + diagnostic_attempts],
        default=None,
    )
    last_activity_days = None
    if latest_activity is not None:
        last_activity_days = (datetime.now(timezone.utc).date() - latest_activity.date()).days

    points = (
        sum(attempt.correct_answers * 10 for attempt in test_attempts)
        + sum(attempt.correct_answers * 12 for attempt in exam_attempts)
        + sum(attempt.correct_answers * 8 for attempt in diagnostic_attempts)
    )
    plan = ensure_learning_plan(db, current_user.id)
    plan_payload = build_learning_plan_response(db, plan)
    next_step = plan_payload.get("next_step") or build_next_step(db=db, user_id=current_user.id, weak_topic_ids=progress.weak_topics)
    daily_plan = plan_payload.get("today_plan") or []
    if not daily_plan:
        latest_scores = _latest_scores_by_topic(test_attempts)
        mistake_topic_id = _latest_mistake_topic_id(test_attempts)
        daily_plan = _build_daily_plan(
            topics=topics,
            weak_topics=weak_topics,
            latest_scores=latest_scores,
            mistake_topic_id=mistake_topic_id,
        )

    topics_remaining = max(int(progress.total_topics) - int(progress.mastered_topics), 0)
    purchased_course_ids = {
        value[0]
        for value in db.query(CoursePurchase.course_id).filter(CoursePurchase.user_id == current_user.id).all()
    }
    recommended_course_query = db.query(Course).filter(Course.is_active.is_(True))
    if purchased_course_ids:
        recommended_course_query = recommended_course_query.filter(Course.id.notin_(purchased_course_ids))
    recommended_course = recommended_course_query.order_by(Course.price_rub.asc(), Course.id.asc()).first()

    if topics_remaining > 0:
        motivation_message = (
            f"Ты уже прошёл {progress.percent}% курса. Осталось {topics_remaining} тем до финишной готовности."
        )
    else:
        motivation_message = "Ты закрыл все темы. Закрепи результат пробником и держи темп."

    notification_created = False
    if next_step:
        recommendation_notification = create_notification_once_per_day(
            db=db,
            user_id=current_user.id,
            notification_type="new_recommendation",
            title="Новая рекомендация по обучению",
            body=str(next_step.get("description", "Продолжай обучение по персональной траектории.")),
            href=str(next_step.get("href", "/dashboard")),
        )
        if recommendation_notification is not None:
            notification_created = True

    if isinstance(last_activity_days, int) and last_activity_days >= 2:
        inactivity_notification = create_notification_once_per_day(
            db=db,
            user_id=current_user.id,
            notification_type="inactivity_reminder",
            title="Пора вернуться к подготовке",
            body=f"Ты не заходил {last_activity_days} дн. Вернись в ритм и продолжи обучение.",
            href="/dashboard",
        )
        if inactivity_notification is not None:
            notification_created = True

    if notification_created:
        db.commit()

    upcoming_deadlines_rows = (
        db.query(UserDeadline)
        .filter(UserDeadline.user_id == current_user.id, UserDeadline.is_done.is_(False))
        .order_by(UserDeadline.due_at.asc(), UserDeadline.id.asc())
        .limit(4)
        .all()
    )

    profile_summary = {
        "nickname": current_user.nickname,
        "email": current_user.email,
        "date_of_birth": current_user.date_of_birth.isoformat() if current_user.date_of_birth else None,
        "role": current_user.role.value,
        "onboarding_completed_at": (
            current_user.onboarding_completed_at.isoformat() if current_user.onboarding_completed_at else None
        ),
    }
    activity_summary = {
        "test_attempts_count": len(test_attempts),
        "exam_attempts_count": len(exam_attempts),
        "diagnostic_attempts_count": len(diagnostic_attempts),
        "learning_sessions_total_seconds": int(
            sum(int(getattr(attempt, "duration_seconds", 0) or 0) for attempt in test_attempts + exam_attempts)
        ),
        "last_activity_days": last_activity_days,
    }

    return DashboardOut(
        full_name=current_user.full_name,
        progress_percent=progress.percent,
        topics_total=progress.total_topics,
        topics_mastered=progress.mastered_topics,
        topics_remaining=topics_remaining,
        latest_exam_result=latest_exam_result,
        weak_topics=[{"id": t.id, "title": t.title} for t in weak_topics],
        strong_topics=strong_topics,
        review_topics=review_topics,
        streak_days=streak_days,
        points=points,
        next_step=next_step,
        daily_plan=daily_plan,
        last_activity_days=last_activity_days,
        motivation_message=motivation_message,
        recommended_course=(
            {
                "id": recommended_course.id,
                "title": recommended_course.title,
                "href": "/courses",
                "description": "Рекомендуем подключить этот курс для системной подготовки.",
            }
            if recommended_course
            else None
        ),
        forecast={
            "index": float(plan.forecast_index),
            "trend": float(plan.forecast_trend),
            "remaining_to_goal": int(plan.remaining_to_goal),
        },
        profile_summary=profile_summary,
        activity_summary=activity_summary,
        upcoming_deadlines=[
            {
                "id": row.id,
                "title": row.title,
                "item_type": row.item_type.value,
                "due_at": row.due_at,
                "urgency": row.urgency.value,
                "is_done": row.is_done,
            }
            for row in upcoming_deadlines_rows
        ],
        test_attempts=[
            HistoryItem(id=a.id, score_percent=a.score_percent, created_at=a.created_at, topic_id=a.topic_id)
            for a in test_attempts
        ],
        exam_attempts=[
            HistoryItem(id=a.id, score_percent=a.score_percent, created_at=a.created_at, topic_id=None)
            for a in exam_attempts
        ],
    )
