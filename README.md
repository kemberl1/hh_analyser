# HH Analyser

> Web-приложение для анализа IT-вакансий с hh.ru — зарплаты, навыки, грейды, работодатели, динамика рынка.

## 🏗 Структура проекта

```
hh_analyser/
├── backend/               # FastAPI backend
│   ├── app/
│   │   ├── api/           # REST endpoints (routers)
│   │   │   └── v1/        # API v1
│   │   ├── core/          # Config, logging
│   │   ├── db/            # SQLAlchemy engine, session, base
│   │   ├── models/        # ORM models
│   │   ├── repositories/  # Data access layer
│   │   ├── schemas/       # Pydantic schemas (DTOs)
│   │   ├── services/      # Business logic
│   │   ├── scheduler/     # APScheduler entrypoint
│   │   └── main.py        # FastAPI app entry
│   ├── alembic/           # Database migrations
│   ├── tests/             # pytest tests
│   ├── alembic.ini
│   ├── Dockerfile
│   ├── requirements.txt
│   └── pyproject.toml
├── frontend/              # React + Vite + TypeScript
│   ├── src/
│   ├── public/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   └── tailwind.config.js
├── docs/                  # Specification (Phase 0)
├── docker-compose.yml     # Full stack orchestration
├── .env.example           # Environment variables template
├── .gitignore
└── README.md
```

## 🚀 Быстрый запуск (Docker)

### 1. Клонируйте репозиторий и создайте `.env`

```bash
cp .env.example .env
# Отредактируйте .env при необходимости (пароли, API_KEY)
```

### 2. Запустите все сервисы

```bash
docker compose up --build
```

Это поднимет:
- **db** — PostgreSQL 16 на порту `5432`
- **migrations** — Alembic `upgrade head` (выполнится и завершится)
- **api** — FastAPI на `http://localhost:8000`
- **scheduler** — APScheduler worker (heartbeat каждые 60с)
- **frontend** — Vite dev server на `http://localhost:5173`

### 3. Проверьте работоспособность

```bash
# Backend health (доступен и как /api/v1/health, и как /health)
curl http://localhost:8000/api/v1/health
# → {"status":"ok","db":"ok"}

# Frontend
open http://localhost:5173
```

> **Важно:** Docker-образы бейкают код на build-time. После изменений в коде перед запуском нужна пересборка: `docker compose build`.

### 4. Сбор данных и метрики (CLI)

```bash
# Внутри backend-образа / окружения:
python -m app.cli ingest [--max-pages N]   # запуск пайплайна сбора (HTML primary)
python -m app.cli seed                      # сид словарей relevance_terms
python -m app.cli rebuild-snapshots         # пересчёт предрассчитанных метрик (snapshots)
python -m app.scheduler.main --run-now      # разовый прогон scheduler (без cron-цикла)
```

## 🛠 Локальный запуск без Docker

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Настройте DATABASE_URL на локальный PostgreSQL
export DATABASE_URL="postgresql+psycopg://hh_analyser:changeme@localhost:5432/hh_analyser"

# Миграции
alembic upgrade head

# Запуск API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Запуск Scheduler (отдельный терминал)
python -m app.scheduler.main            # cron-режим
python -m app.scheduler.main --run-now  # разовый прогон и выход

# CLI: сбор данных и метрики
python -m app.cli ingest [--max-pages N]
python -m app.cli seed
python -m app.cli rebuild-snapshots
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Откройте `http://localhost:5173`.

### Тесты

```bash
cd backend
pytest tests/ -v
```

## 📋 Переменные окружения

| Переменная | Описание | Default |
|------------|----------|---------|
| `POSTGRES_USER` | Пользователь PostgreSQL | `hh_analyser` |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL | `changeme` |
| `POSTGRES_DB` | Название БД | `hh_analyser` |
| `DATABASE_URL` | SQLAlchemy connection string | `postgresql+psycopg://...@db:5432/hh_analyser` |
| `APP_ENV` | Окружение (development/production) | `development` |
| `LOG_LEVEL` | Уровень логов | `INFO` |
| `CORS_ORIGINS` | Разрешённые CORS-origins (JSON) | `["http://localhost:5173","http://localhost:3000"]` |
| `API_KEY` | Ключ LLM API (X5 CoPilot) | — |
| `LLM_ENABLED` | Включение LLM-фич (инсайты, обогащение резюме) | `true` |
| `LLM_BASE_URL` | URL LLM API | `https://api-copilot.x5.ru/aigw/v1/` |
| `LLM_MODEL` | Модель LLM (чат) | `x5-airun-medium` |
| `LLM_CA_BUNDLE` | Путь к PEM с внутренним CA X5 (TLS-верификация ВКЛ; пусто → системный certifi) | `/app/certs/x5_root_ca.pem` |
| `HH_SOURCE` | Источник сбора: `html` (primary) / `api` | `html` |
| `HH_API_FALLBACK_ENABLED` | Включение фолбэка `api.hh.ru` | `false` |
| `HH_MAX_PAGES` | Лимит страниц поиска при сборе | `20` |
| `SCHEDULER_CRON_HOUR` | Час запуска CRON | `3` |
| `SCHEDULER_CRON_MINUTE` | Минута запуска CRON | `0` |
| `SCHEDULER_TIMEZONE` | Таймзона планировщика | `Europe/Moscow` |
| `SCHEDULER_MAX_PAGES` | Лимит страниц для джобы (пусто → `HH_MAX_PAGES`) | — |
| `SCHEDULER_MISFIRE_GRACE_TIME` | Окно догона пропущенного запуска, сек | `3600` |
| `VITE_API_URL` | URL бэкенда для фронта | `http://localhost:8000` |

> **TLS / LLM_CA_BUNDLE:** X5 CoPilot находится за внутренним корпоративным CA, отсутствующим в публичном `certifi`. При заданном `LLM_CA_BUNDLE` используется кастомный httpx-клиент с этим CA — TLS-верификация **остаётся включённой**. Сертификат в `backend/certs/x5_root_ca.pem` (в `.gitignore`; в проде — секреты K8s). Пустые строки scheduler-переменных безопасно трактуются валидаторами.

## 🔌 Реализованные API-эндпоинты

- `GET /api/v1/health`, `GET /health` — живость + доступность БД (`{status, db}`)
- `GET /api/v1/ingestion/status` — последний прогон + `data_freshness_hours`
- Метрики (8): `/metrics/salary`, `/metrics/salary/timeseries`, `/metrics/skills`, `/metrics/skills/cooccurrence`, `/metrics/employers`, `/metrics/demand`, `/metrics/distribution`, `/metrics/overview`
- `GET /api/v1/insights/market` — LLM-анализ рынка
- `POST /api/v1/resume/analyze` (multipart PDF/DOCX/текст), `POST /api/v1/resume/analyze/text` (JSON)

Все ответы — в конверте `{ meta, data }`; `meta.date_from/date_to` могут быть `null`. Полный контракт — в [`docs/06-api-contract.md`](docs/06-api-contract.md).

## 📚 Документация

> **Статус: MVP реализован (все фазы 0–7).** Спецификация синхронизирована с реализацией.

Спецификация проекта — в папке [`docs/`](docs/):
- [Обзор](docs/00-overview.md)
- [Требования](docs/01-requirements.md)
- [Архитектура](docs/02-architecture.md)
- [Модель данных](docs/03-data-model.md)
- [Метрики](docs/04-metrics.md)
- [Техстек](docs/05-tech-stack.md)
- [API-контракт](docs/06-api-contract.md)
- [Дорожная карта](docs/07-roadmap.md)
- [Индекс docs (статус, как запустить)](docs/README.md)

## License

Private project.
