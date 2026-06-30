from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.social import AchievementsSummaryOut
from app.services.achievements import build_achievements_view

router = APIRouter(prefix="/achievements", tags=["achievements"])


@router.get("", response_model=AchievementsSummaryOut)
def get_achievements(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    payload = build_achievements_view(db=db, user_id=current_user.id)
    return AchievementsSummaryOut(**payload)


@router.post("/sync", response_model=AchievementsSummaryOut)
def sync_achievements(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    payload = build_achievements_view(db=db, user_id=current_user.id)
    return AchievementsSummaryOut(**payload)
