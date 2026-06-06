# 02 — Архитектура системы (Architecture)

> Диаграммы — в Mermaid. Внутри узлов диаграмм не используются кавычки и круглые скобки.

---

## 1. Обзор архитектуры

HH Analyser — это монорепозиторий с тремя исполняемыми сущностями, упакованными в Docker Compose:

1. **Backend API** (FastAPI) — REST-интерфейс для фронтенда; отдаёт агрегированные метрики.
2. **Scheduler** (worker) — ежедневный CRON-процесс: запускает парсер, нормализацию, запись в БД, пересчёт агрегаций.
3. **Frontend** (React + Vite) — дашборды и инфографика.

Хранилище — единая **PostgreSQL**. Внешние зависимости — `api.hh.ru` (+ HTML-фолбэк), источник курсов валют (ЦБ РФ) и LLM-провайдер (X5 CoPilot API, фазы 6–7).

```mermaid
flowchart TB
    subgraph External [Внешние источники]
        HHAPI[api.hh.ru]
        HHWEB[hh.ru HTML страницы]
        CBR[ЦБ РФ курсы валют]
        LLM[X5 CoPilot API LLM]
    end

    subgraph App [HH Analyser Docker Compose]
        FE[Frontend React Vite]
        API[Backend API FastAPI]
        SCHED[Scheduler Worker CRON]
        DB[(PostgreSQL)]
    end

    USER[Пользователь соискатель] --> FE
    FE -->|REST JSON| API
    API -->|SQL чтение| DB
    SCHED -->|SQL запись и upsert| DB
    SCHED -->|HTTP основной путь| HHAPI
    SCHED -->|HTTP фолбэк| HHWEB
    SCHED -->|курсы| CBR
    API -.->|Phase 6 7| LLM
    SCHED -.->|Phase 6| LLM
```

## 2. Компоненты

### 2.1. Parser (источник данных)

- **Назначение:** получить «сырые» вакансии Frontend по РФ.
- **Стратегия:** primary — клиент `api.hh.ru`; fallback — HTML-скрейпер. Выбор стратегии инкапсулирован за общим интерфейсом `VacancySource`.
- **Особенности:** rate-limiting, retry/backoff, идентифицирующий `User-Agent`, сохранение `raw_payload`.

### 2.2. Normalizer (нормализация)

- Приводит сырые данные к доменной модели: валюты, gross/net, грейд, канонизация навыков, формат работы, опыт.
- Детерминированная и тестируемая логика (без сети).

### 2.3. Ingestion / Persistence (запись в БД)

- Идемпотентный **upsert** по `hh_vacancy_id`.
- Ведёт журнал прогонов `ingestion_runs`.
- Разделяет «факт вакансии» и связи (skills, employer, salary).

### 2.4. Scheduler (планировщик)

- Запуск ежедневно по CRON. В MVP — APScheduler внутри worker-процесса (альтернатива — системный cron, см. [`05-tech-stack.md`](05-tech-stack.md)).
- Оркестрирует пайплайн: parse → normalize → persist → aggregate.

### 2.5. Aggregation (агрегации/метрики)

- Считает метрики по `published_at` и сохраняет предрассчитанные **snapshots** по периодам (день/неделя/месяц/год) и срезам (грейд, валюта, gross/net).
- Пересчёт после каждого прогона; атомарная замена снапшотов.

### 2.6. API layer (FastAPI)

- Read-ориентированные эндпоинты для дашбордов с фильтрами.
- Слои: `routers` → `services` → `repositories` → `models`.

### 2.7. LLM-adapter (фазы 6–7)

- Абстрактный интерфейс `LLMClient` (методы `chat`, `embeddings`).
- Реализация `X5CopilotClient` поверх OpenAI-совместимого API (`base_url`, `Authorization: Bearer API_KEY`).
- Провайдер заменяем без изменения бизнес-логики (NFR-28).

### 2.8. Frontend (React + Vite)

- Презентационный слой: дашборды, графики, фильтры.
- Данные через REST; кэш — TanStack Query; собственного хранилища нет.

## 3. Слои бэкенда (layered architecture)

```mermaid
flowchart TB
    R[Routers API FastAPI] --> S[Services бизнес логика]
    S --> RepoR[Repositories чтение]
    S --> RepoW[Repositories запись]
    RepoR --> M[(ORM Models SQLAlchemy)]
    RepoW --> M
    M --> PG[(PostgreSQL)]

    subgraph Ingestion [Пайплайн сбора]
        P[Parser VacancySource] --> N[Normalizer]
        N --> ING[Ingestion Service]
        ING --> RepoW
        AGG[Aggregation Service] --> RepoW
    end

    subgraph LLMBlock [LLM Phase 6 7]
        LA[LLM Adapter интерфейс] --> X5[X5 Copilot Client]
    end

    S -.-> LA
    SCHEDULER[Scheduler CRON] --> P
    SCHEDULER --> AGG
```

| Слой | Ответственность | Не должен |
|------|------------------|-----------|
| Routers | HTTP, валидация query/body, сериализация | Содержать бизнес-логику |
| Services | Бизнес-логика, оркестрация | Знать про HTTP/SQL детали |
| Repositories | Доступ к данным (CRUD, запросы) | Содержать бизнес-правила |
| Models | ORM-схема, типы | Содержать логику представления |
| Adapters | Внешние интеграции (LLM, источники) | Утекать наружу деталями провайдера |

## 4. Поток данных: ежедневный сбор (ingestion flow)

```mermaid
sequenceDiagram
    participant CRON as Scheduler CRON
    participant SRC as VacancySource
    participant HH as api.hh.ru
    participant NRM as Normalizer
    participant DB as PostgreSQL
    participant AGG as Aggregation

    CRON->>DB: создать запись ingestion_runs статус running
    CRON->>SRC: запросить список Frontend вакансий РФ
    SRC->>HH: GET vacancies с фильтрами и пагинацией
    alt API доступен
        HH-->>SRC: список вакансий JSON
    else API недоступен
        SRC->>SRC: фолбэк на HTML скрейпинг
    end
    loop по каждой вакансии
        SRC->>HH: GET vacancies id детали
        HH-->>SRC: детали вакансии
        SRC->>NRM: сырые данные
        NRM->>NRM: валюта grade skills формат
        NRM->>DB: upsert по hh_vacancy_id
    end
    CRON->>AGG: пересчитать снапшоты по published_at
    AGG->>DB: атомарно заменить snapshots
    CRON->>DB: обновить ingestion_runs статус success
```

## 5. Поток данных: запрос дашборда (read flow)

```mermaid
sequenceDiagram
    participant U as Пользователь
    participant FE as Frontend
    participant API as FastAPI
    participant DB as PostgreSQL

    U->>FE: открыть дашборд выбрать фильтры период grade валюта
    FE->>API: GET metrics salary с query параметрами
    API->>DB: чтение предрассчитанных snapshots
    DB-->>API: агрегированные значения
    API-->>FE: JSON метрики
    FE->>U: графики и инфографика
```

## 6. Поток данных: LLM-фичи (Phase 6–7, проектно)

```mermaid
flowchart LR
    subgraph Phase6 [Phase 6 анализ рынка]
        AGG2[Агрегаты рынка] --> PR[Prompt Builder]
        PR --> LA2[LLM Adapter]
        LA2 --> X52[X5 Copilot chat]
        X52 --> INS[Текстовые инсайты]
    end

    subgraph Phase7 [Phase 7 анализ резюме]
        RES[Резюме пользователя] --> SAN[Санитизация PII]
        SAN --> EMB[Embeddings]
        EMB --> SIM[Сопоставление с рынком]
        SAN --> LA3[LLM Adapter chat]
        SIM --> SCORE[Оценка профпригодности]
        LA3 --> SCORE
    end
```

## 7. Развёртывание (deployment, Docker Compose)

```mermaid
flowchart TB
    subgraph Compose [docker-compose]
        C1[service api FastAPI uvicorn]
        C2[service scheduler worker]
        C3[service frontend nginx статика Vite build]
        C4[(service db postgres)]
        C5[service migrations alembic upgrade head]
    end
    C5 --> C4
    C1 --> C4
    C2 --> C4
    C3 --> C1
```

- `migrations` выполняет `alembic upgrade head` перед стартом `api`/`scheduler`.
- Секреты (`API_KEY`, строка подключения к БД) — через env-файл, не в образах.

## 8. Ключевые архитектурные решения (ADR-сводка)

| # | Решение | Обоснование |
|---|---------|-------------|
| AD-1 | Разделение API и Scheduler на отдельные процессы | Изоляция нагрузки сбора от обслуживания запросов; независимое масштабирование |
| AD-2 | Предрасчёт снапшотов вместо запросов на лету | Производительность дашбордов (NFR-1, NFR-2) |
| AD-3 | Интерфейс `VacancySource` с primary/fallback | Устойчивость к изменениям hh.ru (FR-3) |
| AD-4 | Хранение `raw_payload` | Переобработка без повторного парсинга (FR-8) |
| AD-5 | Абстрактный `LLMClient` | Заменяемость провайдера (NFR-28) |
| AD-6 | Ось времени = `published_at` | Корректная рыночная статистика (FR-11) |
| AD-7 | Upsert по `hh_vacancy_id` | Идемпотентность сбора (FR-4) |
