"""Добавляем src/ в путь импорта для тестов (src-layout без установки пакета)."""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
