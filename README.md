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
# Backend health
curl http://localhost:8000/api/v1/health
# → {"status":"ok","db":"ok"}

# Frontend
open http://localhost:5173
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
python -m app.scheduler.main
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
| `CORS_ORIGINS` | Разрешённые CORS-origins (JSON) | `["http://localhost:5173"]` |
| `API_KEY` | Ключ LLM API (Phase 6+) | — |
| `LLM_BASE_URL` | URL LLM API | `https://api-copilot.x5.ru/aigw/v1/` |
| `LLM_MODEL` | Модель LLM | `x5-airun-medium` |
| `SCHEDULER_CRON_HOUR` | Час запуска CRON | `3` |
| `SCHEDULER_CRON_MINUTE` | Минута запуска CRON | `0` |
| `VITE_API_URL` | URL бэкенда для фронта | `http://localhost:8000` |

## 📚 Документация

Спецификация проекта — в папке [`docs/`](docs/):
- [Обзор](docs/00-overview.md)
- [Требования](docs/01-requirements.md)
- [Архитектура](docs/02-architecture.md)
- [Модель данных](docs/03-data-model.md)
- [Метрики](docs/04-metrics.md)
- [Техстек](docs/05-tech-stack.md)
- [API-контракт](docs/06-api-contract.md)
- [Дорожная карта](docs/07-roadmap.md)

## License

Private project.
