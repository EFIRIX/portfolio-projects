import random

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.currency import CurrencyReason
from app.models.exam_attempt import ExamAttempt
from app.models.learning_response import LearningResponseSourceType
from app.models.learning_session import LearningActivityType, LearningSession
from app.models.question import Question, QuestionType
from app.models.user import User
from app.schemas.progress import HistoryItem
from app.schemas.question import AttemptResultOut, QuestionOut, SubmitExamRequest, TestMode
from app.services.gamification import add_currency_transaction
from app.services.learning_path import recalculate_learning_plan
from app.services.learning_response import create_or_get_learning_response
from app.services.question_picker import pick_global_questions
from app.services.social import create_notification

router = APIRouter(prefix="/exam", tags=["exam"])


@router.get("/start", response_model=list[QuestionOut])
def exam_start(
    mode: TestMode = Query(default=TestMode.standard),
    limit: int = Query(default=24, ge=12, le=60),
    auto_first: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolved_mode = mode
    if auto_first:
        first_attempt = (
            db.query(ExamAttempt.id)
            .filter(ExamAttempt.user_id == current_user.id)
            .order_by(ExamAttempt.id.asc())
            .first()
        )
        if first_attempt is None:
            resolved_mode = random.choice([TestMode.easy, TestMode.standard, TestMode.hard])

    questions = pick_global_questions(
        db=db,
        question_type=QuestionType.exam,
        mode=resolved_mode.value,
        limit=limit,
        user_id=current_user.id,
        ensure_topic_mix=True,
    )
    return questions


@router.post("/submit", response_model=AttemptResultOut)
def exam_submit(
    payload: SubmitExamRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.question_ids:
        unique_ids = list(dict.fromkeys(payload.question_ids))
        questions = (
            db.query(Question)
            .filter(Question.id.in_(unique_ids), Question.type == QuestionType.exam)
            .all()
        )
    else:
        questions = (
            db.query(Question)
            .filter(Question.type == QuestionType.exam)
            .order_by(Question.id.asc())
            .limit(24)
            .all()
        )
    if not questions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Вопросы для пробника не найдены")

    answers_map = {answer.question_id: answer.selected_option for answer in payload.answers}
    details: list[dict] = []
    correct_answers = 0

    for question in questions:
        selected = answers_map.get(question.id)
        is_correct = selected == question.correct_option
        if is_correct:
            correct_answers += 1
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

    total_questions = len(questions)
    score_percent = round((correct_answers / total_questions) * 100, 2) if total_questions else 0.0

    attempt = ExamAttempt(
        user_id=current_user.id,
        score_percent=score_percent,
        total_questions=total_questions,
        correct_answers=correct_answers,
        duration_seconds=payload.duration_seconds,
        details=details,
    )
    db.add(attempt)
    db.flush()
    db.add(
        LearningSession(
            user_id=current_user.id,
            topic_id=None,
            activity_type=LearningActivityType.exam,
            duration_seconds=payload.duration_seconds,
            metadata_json={"score_percent": score_percent, "attempt_type": "exam"},
        )
    )
    add_currency_transaction(
        db,
        user_id=current_user.id,
        amount=max(10, int(correct_answers * 3)),
        reason=CurrencyReason.exam,
        payload={"score_percent": score_percent},
    )
    create_notification(
        db=db,
        user_id=current_user.id,
        notification_type="exam_result_ready",
        title="Результат пробника готов",
        body=f"Твой результат: {score_percent}% ({correct_answers}/{total_questions}).",
        href="/exam",
    )
    learning_response = create_or_get_learning_response(
        db,
        student_id=current_user.id,
        source_type=LearningResponseSourceType.exam,
        source_ref=str(attempt.id),
        exam_attempt_id=attempt.id,
    )
    db.commit()
    recalculate_learning_plan(db, current_user.id)
    db.commit()

    return AttemptResultOut(
        score_percent=score_percent,
        total_questions=total_questions,
        correct_answers=correct_answers,
        details=details,
        learning_response_id=learning_response.id,
    )


@router.get("/history", response_model=list[HistoryItem])
def exam_history(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    attempts = (
        db.query(ExamAttempt)
        .filter(ExamAttempt.user_id == current_user.id)
        .order_by(ExamAttempt.created_at.desc())
        .limit(20)
        .all()
    )
    return [
        HistoryItem(id=a.id, score_percent=a.score_percent, created_at=a.created_at, topic_id=None)
        for a in attempts
    ]
