from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.course import Course, CoursePurchase, CoursePurchaseStatus
from app.models.user import User
from app.schemas.course import CourseOut, CoursePurchaseActionOut, CoursePurchaseWithCourseOut
from app.services.social import create_notification

router = APIRouter(prefix="/courses", tags=["courses"])
SHORT_PRIVATE_CACHE = "private, max-age=120"


def _serialize_course(course: Course, purchase: Optional[CoursePurchase] = None) -> CourseOut:
    access_status = "available"
    if purchase:
        if purchase.status == CoursePurchaseStatus.purchased:
            access_status = "purchased"
        elif purchase.status == CoursePurchaseStatus.in_progress:
            access_status = "in_progress"
        elif purchase.status == CoursePurchaseStatus.completed:
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


@router.get("", response_model=list[CourseOut])
def list_courses(
    level: Optional[str] = Query(default=None),
    only_available: bool = Query(default=False),
    search: Optional[str] = Query(default=None),
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if response is not None:
        response.headers["Cache-Control"] = SHORT_PRIVATE_CACHE
    query = db.query(Course).filter(Course.is_active.is_(True))

    if level:
        query = query.filter(Course.level == level)
    if search:
        term = f"%{search.strip().lower()}%"
        query = query.filter(func.lower(Course.title).like(term))

    courses = query.order_by(Course.created_at.desc(), Course.id.desc()).all()
    if not courses:
        return []

    purchases = (
        db.query(CoursePurchase)
        .filter(CoursePurchase.user_id == current_user.id, CoursePurchase.course_id.in_([course.id for course in courses]))
        .all()
    )
    purchase_map = {purchase.course_id: purchase for purchase in purchases}

    payload = [_serialize_course(course, purchase_map.get(course.id)) for course in courses]
    if only_available:
        payload = [item for item in payload if item.access_status == "available"]
    return payload


@router.get("/mine", response_model=list[CoursePurchaseWithCourseOut])
def my_courses(
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if response is not None:
        response.headers["Cache-Control"] = SHORT_PRIVATE_CACHE
    purchases = (
        db.query(CoursePurchase)
        .filter(CoursePurchase.user_id == current_user.id)
        .order_by(CoursePurchase.purchased_at.desc(), CoursePurchase.id.desc())
        .all()
    )
    result: list[CoursePurchaseWithCourseOut] = []
    for purchase in purchases:
        result.append(
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
    return result


@router.get("/{course_id}", response_model=CourseOut)
def course_detail(
    course_id: int,
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if response is not None:
        response.headers["Cache-Control"] = SHORT_PRIVATE_CACHE
    course = db.query(Course).filter(Course.id == course_id, Course.is_active.is_(True)).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Курс не найден")

    purchase = (
        db.query(CoursePurchase)
        .filter(CoursePurchase.user_id == current_user.id, CoursePurchase.course_id == course_id)
        .first()
    )
    return _serialize_course(course, purchase)


@router.post("/{course_id}/purchase", response_model=CoursePurchaseActionOut)
def purchase_course(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Купить курс. Идемпотентно: повторный запрос не создаст дубликат."""
    course = db.query(Course).filter(Course.id == course_id, Course.is_active.is_(True)).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Курс не найден")

    # Используем FOR UPDATE для предотвращения race conditions при одновременных покупках
    purchase = (
        db.query(CoursePurchase)
        .filter(CoursePurchase.user_id == current_user.id, CoursePurchase.course_id == course_id)
        .with_for_update()
        .first()
    )

    message: str
    if purchase is None:
        purchase = CoursePurchase(
            user_id=current_user.id,
            course_id=course_id,
            status=CoursePurchaseStatus.purchased,
        )
        db.add(purchase)
        message = "Курс успешно куплен и открыт"
        create_notification(
            db=db,
            user_id=current_user.id,
            notification_type="course_purchase",
            title="Курс добавлен в ваши покупки",
            body=f"Курс «{course.title}» доступен в разделе «Мои курсы».",
            href="/courses",
        )
    else:
        if purchase.status == CoursePurchaseStatus.completed:
            message = "Курс уже завершён и доступен в истории"
        elif purchase.status == CoursePurchaseStatus.purchased:
            message = "Курс уже куплен и доступен"
        else:
            purchase.status = CoursePurchaseStatus.purchased
            db.add(purchase)
            message = "Доступ к курсу подтверждён"

    db.commit()
    db.refresh(purchase)

    return CoursePurchaseActionOut(
        message=message,
        purchase=CoursePurchaseWithCourseOut(
            id=purchase.id,
            user_id=purchase.user_id,
            course_id=purchase.course_id,
            status=purchase.status,
            purchased_at=purchase.purchased_at,
            updated_at=purchase.updated_at,
            course=_serialize_course(course, purchase=purchase),
        ),
    )


@router.get("/purchases/history", response_model=list[CoursePurchaseWithCourseOut])
def purchase_history(
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if response is not None:
        response.headers["Cache-Control"] = SHORT_PRIVATE_CACHE
    purchases = (
        db.query(CoursePurchase)
        .filter(CoursePurchase.user_id == current_user.id)
        .order_by(CoursePurchase.purchased_at.desc(), CoursePurchase.id.desc())
        .all()
    )

    return [
        CoursePurchaseWithCourseOut(
            id=purchase.id,
            user_id=purchase.user_id,
            course_id=purchase.course_id,
            status=purchase.status,
            purchased_at=purchase.purchased_at,
            updated_at=purchase.updated_at,
            course=_serialize_course(purchase.course, purchase=purchase),
        )
        for purchase in purchases
    ]
