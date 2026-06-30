from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_staff_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.learning import ForecastOut, LearningPlanOut, LearningPlanRecalculateOut
from app.services.learning_path import (
    build_learning_plan_response,
    calculate_forecast,
    ensure_learning_plan,
    recalculate_learning_plan,
)
from app.services.progress import recalculate_progress

router = APIRouter(prefix="/learning-plan", tags=["learning-plan"])


@router.get("", response_model=LearningPlanOut)
def get_learning_plan(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = ensure_learning_plan(db, current_user.id)
    payload = build_learning_plan_response(db, plan)
    return LearningPlanOut(**payload)


@router.post("/recalculate", response_model=LearningPlanRecalculateOut)
def recalculate_plan(
    user_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_user_id = current_user.id
    if user_id is not None:
        _ = get_staff_user(current_user)  # role guard
        target_user_id = user_id

    plan = recalculate_learning_plan(db, target_user_id)
    db.commit()
    db.refresh(plan)
    payload = build_learning_plan_response(db, plan)
    return LearningPlanRecalculateOut(
        recalculated_at=datetime.now(timezone.utc),
        plan=LearningPlanOut(**payload),
    )


@router.get("/forecast", response_model=ForecastOut)
def get_forecast(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    progress = recalculate_progress(db, current_user.id)
    index, trend, based_on = calculate_forecast(db, current_user.id, weak_topics_count=len(progress.weak_topics))
    if index >= 80:
        level = "высокий"
    elif index >= 60:
        level = "уверенный"
    elif index >= 40:
        level = "базовый"
    else:
        level = "стартовый"

    return ForecastOut(
        index=index,
        trend=trend,
        level=level,
        weak_topics_count=len(progress.weak_topics),
        based_on_attempts=based_on,
        updated_at=datetime.now(timezone.utc),
    )
