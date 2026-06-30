from fastapi import APIRouter

from app.api.v1.endpoints import (
    achievements,
    ai_helper,
    admin,
    auth,
    courses,
    deadlines,
    dashboard,
    diagnostic,
    exam,
    forecast,
    files,
    gamification,
    learning_plan,
    learning_responses,
    learning_time,
    milestones,
    notifications,
    onboarding,
    oral,
    parent,
    purchases,
    profile,
    progress,
    support,
    tests,
    topics,
    upload,
)
from app.api.v1.endpoints import search

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(ai_helper.router)
api_router.include_router(courses.router)
api_router.include_router(deadlines.router)
api_router.include_router(purchases.router)
api_router.include_router(dashboard.router)
api_router.include_router(topics.router)
api_router.include_router(tests.router)
api_router.include_router(diagnostic.router)
api_router.include_router(exam.router)
api_router.include_router(forecast.router)
api_router.include_router(progress.router)
api_router.include_router(learning_plan.router)
api_router.include_router(learning_responses.router)
api_router.include_router(learning_time.router)
api_router.include_router(milestones.router)
api_router.include_router(oral.router)
api_router.include_router(gamification.router)
api_router.include_router(admin.router)
api_router.include_router(support.router)
api_router.include_router(notifications.router)
api_router.include_router(onboarding.router)
api_router.include_router(parent.router)
api_router.include_router(profile.router)
api_router.include_router(achievements.router)
api_router.include_router(upload.router)
api_router.include_router(files.router)
api_router.include_router(search.router)
