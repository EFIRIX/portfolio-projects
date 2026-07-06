"""Еженедельный отчёт со сравнением к прошлой неделе и наблюдениями.

Наблюдения обязаны ссылаться на конкретные цифры пользователя (требование ТЗ).
Поэтому:
  * в промпт LLM передаются реальные суммы и проценты изменения;
  * есть детерминированный fallback (_rule_based_insight), который сам
    строит наблюдение с конкретной цифрой, если LLM выключен или упал.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from decimal import Decimal

from .db import Database
from .llm.base import LLMProvider
from .models import CategorySummary, WeeklyReport

logger = logging.getLogger(__name__)


def week_bounds(ref: date) -> tuple[date, date]:
    """Границы недели (пн–вс), в которую попадает ref."""
    start = ref - timedelta(days=ref.weekday())
    return start, start + timedelta(days=6)


def _plural_ops(n: int) -> str:
    """Склонение слова «операция» для русского числительного."""
    if 11 <= n % 100 <= 14:
        return "операций"
    last = n % 10
    if last == 1:
        return "операцию"
    if 2 <= last <= 4:
        return "операции"
    return "операций"


def _pct_change(current: Decimal, previous: Decimal) -> float | None:
    if previous == 0:
        return None
    return float((current - previous) / previous * 100)


def build_report(
    db: Database,
    user_id: int,
    ref_date: date,
    llm: LLMProvider | None = None,
) -> WeeklyReport:
    """Собирает отчёт за неделю ref_date со сравнением к предыдущей."""
    cur_start, cur_end = week_bounds(ref_date)
    prev_start, prev_end = week_bounds(cur_start - timedelta(days=1))

    current = db.summary_between(user_id, cur_start, cur_end)
    previous = db.summary_between(user_id, prev_start, prev_end)

    report = WeeklyReport(
        week_start=cur_start,
        week_end=cur_end,
        current=current,
        previous=previous,
        total_current=sum((c.total for c in current), Decimal(0)),
        total_previous=sum((p.total for p in previous), Decimal(0)),
    )
    report.insights = _make_insights(report, llm)
    return report


def _prev_map(previous: list[CategorySummary]) -> dict[str, Decimal]:
    return {c.category: c.total for c in previous}


def _rule_based_insight(report: WeeklyReport) -> list[str]:
    """Гарантированное наблюдение с конкретной цифрой (без LLM)."""
    if not report.current:
        return ["На этой неделе расходов не зафиксировано."]

    insights: list[str] = []
    prev = _prev_map(report.previous)
    top = max(report.current, key=lambda c: c.total)
    insights.append(
        f"Больше всего вы потратили на «{top.category}» — {top.total:.0f} ₽ "
        f"за {top.count} {_plural_ops(top.count)}."
    )

    # Ищем категорию с максимальным ростом к прошлой неделе.
    changes = []
    for c in report.current:
        pct = _pct_change(c.total, prev.get(c.category, Decimal(0)))
        if pct is not None:
            changes.append((pct, c))
    if changes:
        pct, c = max(changes, key=lambda x: x[0])
        if pct > 0:
            was = prev[c.category]
            insights.append(
                f"Расходы на «{c.category}» выросли на {pct:.0f}% "
                f"({was:.0f} ₽ → {c.total:.0f} ₽)."
            )
    return insights


def _make_insights(report: WeeklyReport, llm: LLMProvider | None) -> list[str]:
    baseline = _rule_based_insight(report)
    if llm is None or not report.current:
        return baseline

    prev = _prev_map(report.previous)
    lines = []
    for c in report.current:
        pct = _pct_change(c.total, prev.get(c.category, Decimal(0)))
        pct_txt = f"{pct:+.0f}%" if pct is not None else "нет данных за прошлую неделю"
        lines.append(f"- {c.category}: {c.total:.0f} ₽ ({c.count} операций), изменение {pct_txt}")

    prompt = (
        "Вот траты пользователя за неделю по категориям:\n"
        + "\n".join(lines)
        + f"\n\nИтого за неделю: {report.total_current:.0f} ₽, "
        f"прошлая неделя: {report.total_previous:.0f} ₽.\n\n"
        "Дай 1-2 коротких содержательных наблюдения на русском. Каждое ОБЯЗАНО "
        "ссылаться на конкретную цифру или процент из данных выше. Без общих "
        "фраз и советов «вообще». Ответ — JSON-массив строк."
    )
    system = "Ты финансовый аналитик. Отвечаешь кратко, только фактами из данных."

    try:
        raw = llm.complete(prompt, system=system)
        insights = _parse_insights(raw)
        if insights:
            return insights
    except Exception as exc:  # noqa: BLE001 - деградируем к rule-based
        logger.warning("Не удалось получить наблюдения от LLM: %s", exc)
    return baseline


def _parse_insights(raw: str) -> list[str]:
    text = (raw or "").strip()
    first, last = text.find("["), text.rfind("]")
    if first != -1 and last != -1 and last > first:
        text = text[first : last + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Модель ответила простым текстом — вернём построчно.
        return [ln.strip("-• ").strip() for ln in raw.splitlines() if ln.strip()][:2]
    return [str(x).strip() for x in data if str(x).strip()][:2] if isinstance(data, list) else []


def format_report(report: WeeklyReport) -> str:
    """Готовит текст отчёта для отправки в Telegram (Markdown)."""
    start = report.week_start.strftime("%d.%m")
    end = report.week_end.strftime("%d.%m.%Y")
    lines = [f"📊 *Отчёт за неделю {start}–{end}*", ""]

    if not report.current:
        lines.append("За эту неделю расходов не найдено.")
        return "\n".join(lines)

    prev = _prev_map(report.previous)
    for c in report.current:
        pct = _pct_change(c.total, prev.get(c.category, Decimal(0)))
        if pct is None:
            trend = "🆕"
        elif pct > 0:
            trend = f"🔺 +{pct:.0f}%"
        elif pct < 0:
            trend = f"🔻 {pct:.0f}%"
        else:
            trend = "➡️ 0%"
        lines.append(f"• {c.category}: *{c.total:.0f} ₽* ({c.count} шт.)  {trend}")

    lines.append("")
    total_pct = _pct_change(report.total_current, report.total_previous)
    total_trend = f" ({total_pct:+.0f}% к прошлой неделе)" if total_pct is not None else ""
    lines.append(f"💰 Всего: *{report.total_current:.0f} ₽*{total_trend}")

    if report.insights:
        lines.append("")
        lines.append("🧠 *Наблюдения:*")
        for ins in report.insights:
            lines.append(f"— {ins}")

    return "\n".join(lines)
