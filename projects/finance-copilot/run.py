"""Запуск бота без установки пакета: `python run.py`."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from finance_copilot.bot.main import main  # noqa: E402

if __name__ == "__main__":
    main()
