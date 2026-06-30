# Интелла — система подготовки к ОГЭ по истории

Платформа на **Next.js + FastAPI + PostgreSQL** с акцентом на персональный маршрут и контур **устного допуска**.

## Что добавлено в Oral Admission Upgrade v1

- Новый контур **«Устный допуск»** без ломки существующих auth/API сценариев.
- Импорт банка заданий из DOCX в БД (идемпотентно):
  - `250` коротких вопросов (`SHORT_Q`)
  - `60` заданий с текстом (`TEXT_TASK`)
  - `40` устных билетов (`ORAL_TICKET`)
- Новые сущности: oral tasks/attempts/responses/readiness/checkpoints.
- Новые API для тренировки, мини-экзамена, проверки и readiness.
- Минимальный frontend-контур `/oral*` (student + review для curator/methodist).

## Стек

- Frontend: Next.js 16, React, TypeScript, Tailwind
- Backend: FastAPI, SQLAlchemy, Alembic
- База: PostgreSQL (в dev допустим SQLite)
- Хранилище вложений: S3-совместимое (MinIO)
- Инфраструктура: Docker Compose

## Быстрый старт (Docker)

```bash
cp .env.example .env
# заполните SECRET_KEY и пароли

docker compose up -d --build
```

Проверка:

```bash
docker compose ps
curl http://localhost:8000/health
open http://localhost:3000
```

## Локальный запуск

### Backend

```bash
cd backend
cp .env.example .env

python3 -m venv ../.venv
source ../.venv/bin/activate
pip install -r requirements.txt

alembic upgrade head
python -m app.scripts.seed
python -m app.scripts.run_server
```

### Frontend

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

## Импорт DOCX (главная фича)

Файл пользователя:

`/Users/timka/Downloads/Сборник тренировочных заданий по истории России для предполагаемого обязательного устного экзамена в.docx`

### Dry-run

```bash
cd backend
../.venv/bin/python -m app.scripts.import_oral_docx \
  --path "/Users/timka/Downloads/Сборник тренировочных заданий по истории России для предполагаемого обязательного устного экзамена в.docx" \
  --dry-run
```

### Полный импорт

```bash
cd backend
../.venv/bin/python -m app.scripts.import_oral_docx \
  --path "/Users/timka/Downloads/Сборник тренировочных заданий по истории России для предполагаемого обязательного устного экзамена в.docx"
```

Скрипт:

- валидирует counts `250/60/40` (strict-gate)
- выполняет upsert (повторный запуск не дублирует)
- выводит отчёт: `created/updated/skipped/duplicates/errors`

## Новые API (oral-контур)

- `GET /api/v1/oral/tasks?type=&topic=&difficulty=&q=`
- `GET /api/v1/oral/tasks/{id}`
- `POST /api/v1/oral/attempts/start`
- `POST /api/v1/oral/attempts/{id}/submit`
- `POST /api/v1/oral/responses`
- `GET /api/v1/oral/responses/history`
- `GET /api/v1/oral/review/queue`
- `PATCH /api/v1/oral/responses/{id}/status`
- `GET /api/v1/readiness`
- `POST /api/v1/checkpoints/start`
- `POST /api/v1/checkpoints/{id}/submit`

Все существующие endpoint’ы сохранены (backward-compatible).

## Frontend страницы oral

- `/oral` — главная режима «Устный допуск»
- `/oral/tasks` — список заданий с фильтрами
- `/oral/tasks/[id]` — выполнение задания
- `/oral/checkpoints` — контрольные точки
- `/oral/review` — очередь проверки для curator/methodist

## Тесты и quality gates

```bash
# backend
source .venv/bin/activate
pytest backend/tests -q

# frontend
cd frontend
npm run lint
npm run build
```

## Конфигурация

Ключевые переменные окружения:

- `SECRET_KEY` (обязателен, без fallback)
- `DATABASE_URL`
- `COOKIE_SECURE` (`true` в production)
- `COOKIE_SAMESITE`
- `ORAL_EXAM_SIM_LIMIT`
- `ORAL_EXAM_SIM_DURATION_MINUTES`
- `ORAL_TEXT_PASS_THRESHOLD`
- `ORAL_TICKET_PASS_THRESHOLD`

Полный список: [`.env.example`](/Users/timka/Documents/Online_school/.env.example), [`backend/.env.example`](/Users/timka/Documents/Online_school/backend/.env.example), [`frontend/.env.example`](/Users/timka/Documents/Online_school/frontend/.env.example)

## Документация деплоя

См. [`docs/deploy.md`](/Users/timka/Documents/Online_school/docs/deploy.md).

## Netlify + Direct API domain (prod)

Для схемы frontend на Netlify + backend на отдельном HTTPS-домене:

- В Netlify env:
  - `NEXT_PUBLIC_API_URL=https://<backend-domain>/api/v1`
  - `API_SERVER_URL=https://<backend-domain>/api/v1`
  - `NEXT_PUBLIC_API_DEBUG=false`
- В backend env:
  - `CORS_ORIGINS=https://intella-online-school.netlify.app`
  - `COOKIE_SECURE=true`
  - `COOKIE_SAMESITE=none`
  - `CSRF_ENABLED=true`

Важно: для production используйте только стабильный API-домен (Render/Railway/VPS).  
Временные туннели (ngrok) приводят к нестабильным `404`/`CSRF` ошибкам после истечения сессии туннеля.

Проверка связности:

```bash
cd frontend
npm run smoke:prod-api -- --api=https://<backend-domain>/api/v1 --frontend=https://intella-online-school.netlify.app
```
