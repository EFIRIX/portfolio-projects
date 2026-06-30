from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_training_event(
    event: str,
    details: str = "",
    log_path: str | Path = "logs/training_activity.log",
) -> None:
    """Append a training/system activity entry to the log file."""
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    safe_event = str(event).strip() or "event"
    safe_details = str(details).strip()
    line = f"{_utc_now_iso()} | {safe_event}"
    if safe_details:
        line += f" | {safe_details}"

    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_recent_activity(
    log_path: str | Path = "logs/training_activity.log",
    limit: int = 20,
) -> list[str]:
    """Read recent training activity entries from log file."""
    path = Path(log_path)
    if not path.exists():
        return []

    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return lines[-max(1, int(limit)) :]
