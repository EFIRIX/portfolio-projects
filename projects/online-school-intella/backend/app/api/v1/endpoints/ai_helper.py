from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.progress import Progress
from app.models.topic import Topic
from app.models.user import User
from app.schemas.ai_helper import AIExplainOut, AIExplainRequest, AIRecommendationsOut
from app.services.recommendation import build_next_step

router = APIRouter(prefix="/ai-helper", tags=["ai-helper"])


@router.get("/recommendations", response_model=AIRecommendationsOut)
def get_recommendations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    progress = db.query(Progress).filter(Progress.user_id == current_user.id).first()
    weak_ids = progress.weak_topics if progress else []
    weak_topics = (
        db.query(Topic.title).filter(Topic.id.in_(weak_ids)).order_by(Topic.id.asc()).all()
        if weak_ids
        else []
    )
    weak_titles = [row[0] for row in weak_topics]
    next_step = build_next_step(db=db, user_id=current_user.id, weak_topic_ids=weak_ids)

    recommendations = []
    if weak_titles:
        recommendations.append(f"Начни с самой слабой темы: {weak_titles[0]}.")
        recommendations.append("После повторения сразу закрепи тему коротким тестом.")
    else:
        recommendations.append("Поддерживай ритм: 1 тема + 1 тест + 1 мини-повтор карточек в день.")
    recommendations.append("Перед пробником сделай быстрый повтор ключевых дат и терминов.")

    return AIRecommendationsOut(
        next_step_title=next_step.get("title", "Продолжай обучение по плану"),
        recommendations=recommendations,
        weak_topics=weak_titles,
    )


@router.post("/explain", response_model=AIExplainOut)
def explain_mistake(
    payload: AIExplainRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = (db, current_user)  # keep signature explicit for future expansion
    topic_part = f" в теме «{payload.topic_title}»" if payload.topic_title else ""
    if payload.is_correct is True:
        title = "Разбор правильного ответа"
        explanation = f"Отлично! Ты верно ответил{topic_part}. Закрепи успех коротким повтором карточек."
        action_items = [
            "Сделай 3–5 карточек по этой теме.",
            "Перейди к следующему шагу плана.",
        ]
    else:
        title = "Разбор ошибки"
        base = payload.explanation or "Ответ оказался неверным."
        explanation = f"{base} Важно понять логику события{topic_part}: причина → событие → последствия."
        action_items = [
            "Коротко перескажи тему своими словами (3–4 предложения).",
            "Повтори 5 карточек по слабым местам.",
            "Перепройди 1 короткий тест по теме.",
        ]

    return AIExplainOut(title=title, explanation=explanation, action_items=action_items)
