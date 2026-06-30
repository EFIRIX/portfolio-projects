from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.diagnostic_result import DiagnosticResult
from app.models.question import Question, QuestionType
from app.models.topic import Topic
from app.models.user import User
from app.schemas.question import AttemptResultOut, QuestionOut, SubmitDiagnosticRequest, TestMode
from app.services.learning_path import ensure_learning_plan, recalculate_learning_plan
from app.services.progress import recalculate_progress
from app.services.question_picker import pick_global_questions

router = APIRouter(prefix="/diagnostic", tags=["diagnostic"])


def _build_diagnostic_recommendations(*, weak_topics: list[dict], score_percent: float) -> list[str]:
    recommendations: list[str] = []

    if weak_topics:
        first_topic = weak_topics[0]["topic_title"]
        recommendations.append(f"Сначала повтори тему «{first_topic}» и закрепи её карточками.")
    else:
        recommendations.append("Базовый уровень устойчивый: продолжай по текущему маршруту без отката к прошлым темам.")

    if score_percent < 60:
        recommendations.append("Пройди мини-тесты по двум самым слабым темам до результата 70%+.")
    elif score_percent < 80:
        recommendations.append("Сфокусируйся на слабых местах и сделай один мини-экзамен в режиме «стандарт».")
    else:
        recommendations.append("Переходи к усложнённой практике: пробник и контрольная точка по устному допуску.")

    recommendations.append("После следующей попытки сравни динамику в блоке прогресса и обнови следующий шаг.")
    return recommendations[:3]


@router.get("/start", response_model=list[QuestionOut])
def diagnostic_start(
    mode: TestMode = Query(default=TestMode.standard),
    limit: int = Query(default=10, ge=5, le=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    questions = pick_global_questions(
        db=db,
        question_type=QuestionType.diagnostic,
        mode=mode.value,
        limit=limit,
        user_id=current_user.id,
        ensure_topic_mix=True,
    )
    return questions


@router.post("/submit", response_model=AttemptResultOut)
def diagnostic_submit(
    payload: SubmitDiagnosticRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.question_ids:
        unique_ids = list(dict.fromkeys(payload.question_ids))
        questions = (
            db.query(Question)
            .filter(Question.id.in_(unique_ids), Question.type == QuestionType.diagnostic)
            .all()
        )
    else:
        questions = (
            db.query(Question)
            .filter(Question.type == QuestionType.diagnostic)
            .order_by(Question.id.asc())
            .limit(10)
            .all()
        )
    if not questions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Диагностические вопросы не найдены")

    topics = {topic.id: topic for topic in db.query(Topic).all()}
    answers_map = {answer.question_id: answer.selected_option for answer in payload.answers}

    details: list[dict] = []
    correct_answers = 0

    by_topic_total = defaultdict(int)
    by_topic_correct = defaultdict(int)

    for question in questions:
        selected = answers_map.get(question.id)
        is_correct = selected == question.correct_option
        if is_correct:
            correct_answers += 1
            by_topic_correct[question.topic_id] += 1
        by_topic_total[question.topic_id] += 1

        details.append(
            {
                "question_id": question.id,
                "topic_id": question.topic_id,
                "difficulty": question.difficulty.value,
                "text": question.text,
                "selected_option": selected,
                "correct_option": question.correct_option,
                "is_correct": is_correct,
                "explanation": question.explanation,
            }
        )

    weak_topic_ids: list[int] = []
    topic_scores: list[dict] = []

    for topic_id, total in by_topic_total.items():
        score = round((by_topic_correct[topic_id] / total) * 100, 2) if total else 0.0
        topic_scores.append(
            {
                "topic_id": topic_id,
                "topic_title": topics.get(topic_id).title if topic_id in topics else "Неизвестная тема",
                "score_percent": score,
            }
        )
        if score < 60:
            weak_topic_ids.append(topic_id)

    weak_topic_set = set(weak_topic_ids)
    weak_topics = sorted(
        [
            item
            for item in topic_scores
            if isinstance(item.get("topic_id"), int) and int(item["topic_id"]) in weak_topic_set
        ],
        key=lambda item: float(item.get("score_percent") or 0.0),
    )

    total_questions = len(questions)
    score_percent = round((correct_answers / total_questions) * 100, 2) if total_questions else 0.0

    result = DiagnosticResult(
        user_id=current_user.id,
        score_percent=score_percent,
        total_questions=total_questions,
        correct_answers=correct_answers,
        weak_topics=weak_topic_ids,
        details=topic_scores,
    )
    db.add(result)
    db.commit()
    recalculate_progress(db, current_user.id)
    recalculate_learning_plan(db, current_user.id)
    plan = ensure_learning_plan(db, current_user.id)
    db.commit()

    recommendations = _build_diagnostic_recommendations(
        weak_topics=weak_topics,
        score_percent=score_percent,
    )

    return AttemptResultOut(
        score_percent=score_percent,
        total_questions=total_questions,
        correct_answers=correct_answers,
        details=details,
        weak_topics=weak_topics,
        recommendations=recommendations,
        next_step=plan.next_step or None,
    )
