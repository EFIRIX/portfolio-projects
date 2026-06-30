from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.learning import ForecastOut
from app.services.learning_path import calculate_forecast
from app.services.progress import recalculate_progress

router = APIRouter(prefix="/forecast", tags=["forecast"])


@router.get("", response_model=ForecastOut)
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
