from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.currency import CurrencyReason, CurrencyTransaction, WheelSpin
from app.models.user import User
from app.schemas.gamification import CurrencyTransactionOut, WalletOut, WheelSpinOut, WheelStateOut
from app.services.gamification import (
    add_currency_transaction,
    choose_wheel_reward,
    daily_spins_used,
    get_wallet_balance,
)

from app.core.config import settings

router = APIRouter(prefix="/gamification", tags=["gamification"])


def _wallet_payload(db: Session, user_id: int) -> WalletOut:
    spins_used = daily_spins_used(db, user_id)
    return WalletOut(
        balance=get_wallet_balance(db, user_id),
        spin_cost=int(settings.wheel_spin_cost),
        daily_spins_allowed=int(settings.wheel_daily_spins),
        daily_spins_used=spins_used,
        can_spin=spins_used < int(settings.wheel_daily_spins),
    )


@router.get("/wallet", response_model=WalletOut)
def get_wallet(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _wallet_payload(db, current_user.id)


@router.get("/transactions", response_model=list[CurrencyTransactionOut])
def get_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(CurrencyTransaction)
        .filter(CurrencyTransaction.user_id == current_user.id)
        .order_by(CurrencyTransaction.created_at.desc(), CurrencyTransaction.id.desc())
        .limit(200)
        .all()
    )
    return rows


@router.get("/wheel/state", response_model=WheelStateOut)
def get_wheel_state(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    spins_used = daily_spins_used(db, current_user.id)
    can_spin = spins_used < int(settings.wheel_daily_spins)
    return WheelStateOut(
        spin_cost=int(settings.wheel_spin_cost),
        daily_spins_allowed=int(settings.wheel_daily_spins),
        daily_spins_used=spins_used,
        can_spin=can_spin,
        next_available_in_hours=0 if can_spin else 24,
    )


@router.post("/wheel/spin", response_model=WheelSpinOut)
def spin_wheel(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    spins_used = daily_spins_used(db, current_user.id)
    if spins_used >= int(settings.wheel_daily_spins):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Лимит вращений на сегодня исчерпан")

    cost = int(settings.wheel_spin_cost)
    balance = get_wallet_balance(db, current_user.id)
    if balance < cost:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недостаточно монет для вращения")

    add_currency_transaction(
        db,
        user_id=current_user.id,
        amount=-cost,
        reason=CurrencyReason.wheel_cost,
        payload={"at": datetime.now(timezone.utc).isoformat()},
        respect_daily_cap=False,
    )

    reward_type, reward_value, reward_label = choose_wheel_reward()
    if reward_type == "currency_bonus":
        add_currency_transaction(
            db,
            user_id=current_user.id,
            amount=reward_value,
            reason=CurrencyReason.wheel_reward,
            payload={"reward_type": reward_type},
            respect_daily_cap=False,
        )

    db.add(
        WheelSpin(
            user_id=current_user.id,
            cost=cost,
            reward_type=reward_type,
            reward_value=reward_value,
            reward_label=reward_label,
        )
    )
    db.commit()

    return WheelSpinOut(
        message="Колесо фортуны успешно прокручено",
        reward_type=reward_type,
        reward_label=reward_label,
        reward_value=reward_value,
        balance=get_wallet_balance(db, current_user.id),
    )
