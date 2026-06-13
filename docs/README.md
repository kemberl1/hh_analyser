# HH Analyser — Техническая спецификация

> **Статус:** MVP + Phase 8 (Backfill) реализованы (все фазы 0–8 завершены и проверены на живых сервисах). Спецификация синхронизирована с фактической реализацией. 227 бэкенд-тестов зелёные.

Набор документов спецификации web-приложения для сбора и анализа статистики IT-вакансий (Frontend) с hh.ru.

## Содержание

| Документ | Описание |
|----------|----------|
| [`00-overview.md`](00-overview.md) | Обзор продукта, цели, scope MVP, глоссарий |
| [`01-requirements.md`](01-requirements.md) | Функциональные (FR) и нефункциональные (NFR) требования + статусы |
| [`02-architecture.md`](02-architecture.md) | Финальная архитектура, компоненты, диаграммы потоков (Mermaid) |
| [`03-data-model.md`](03-data-model.md) | Модель данных PostgreSQL (миграции 0001–0003), ER-диаграмма |
| [`04-metrics.md`](04-metrics.md) | Каталог метрик M1–M5 с формулами и статусами |
| [`05-tech-stack.md`](05-tech-stack.md) | Финальный техстек, библиотеки, LLM-интеграция (CA-bundle) |
| [`06-api-contract.md`](06-api-contract.md) | REST API контракт (фактически реализованные эндпоинты) |
| [`07-roadmap.md`](07-roadmap.md) | Дорожная карта по фазам (все Completed) + известные ограничения |

## Ключевые принципы (реализовано)

- Сбор данных: **HTML-парсинг hh.ru — основной путь (primary)**; `api.hh.ru` — фолбэк, выключен по умолчанию (`HH_API_FALLBACK_ENABLED=false`). CSS-селекторы в конфиге `HTML_SELECTORS` (скорректированы под дизайн magritte).
- **Backfill (Phase 8):** массовое первичное наполнение — единоразовый полный сбор активных Frontend-вакансий с рекурсивной сегментацией по датам для обхода лимита ~2000 результатов hh.ru; далее ежедневный CRON инкрементально докидывает новые.
- **Relevance Filtering:** нерелевантные вакансии (Fullstack, Backend, PM, QA и т.п.) отсеиваются и не попадают в БД; словари ключевых/стоп-слов конфигурируемы.
- Учёт статистики по дате публикации `published_at` (не перезаписывается при upsert).
- Идемпотентный сбор (dedup по `hh_vacancy_id`).
- Механизм предрасчёта метрик в `snapshots` готов; в MVP эндпоинты считают on-the-fly.
- Заменяемый LLM-провайдер через абстрактный адаптер (X5 CoPilot); TLS-верификация с кастомным `LLM_CA_BUNDLE`.
- Санитизация PII резюме перед LLM; резюме не персистится.
- Scheduler стабилен (оба хотфикса применены); контейнер Up, CRON-докид работает.
- Итеративная поставка: 8 независимо проверяемых фаз (все завершены).

## Как запустить (кратко)

Подробности и переменные окружения — в корневом [`README.md`](../README.md).

```bash
# 1. Конфиг окружения
cp .env.example .env
# при необходимости задать API_KEY и LLM_CA_BUNDLE (для LLM-фич)

# 2. Полный стек (db, migrations, api, scheduler, frontend)
docker compose build        # образы бейкают код на build-time — пересборка обязательна при изменениях
docker compose up

# 3. Миграции (выполняются сервисом migrations автоматически; вручную:)
#    alembic upgrade head   (цепочка 0001 → 0002 → 0003)

# 4. Первичное наполнение (backfill) — РАЗОВАЯ операция
#    Рекомендуется выполнить один раз после первого запуска:
docker compose run --rm api python -m app.cli backfill --days-back 30
#    Затем пересчитать снапшоты:
docker compose run --rm api python -m app.cli rebuild-snapshots
#    После этого ежедневный CRON (scheduler) инкрементально докидывает новые.

# 5. Сбор данных и снапшоты (CLI) — прочие команды
python -m app.cli ingest [--max-pages N]   # запуск пайплайна сбора (HTML primary)
python -m app.cli seed                      # сид словарей relevance_terms
python -m app.cli rebuild-snapshots         # пересчёт предрассчитанных метрик
python -m app.scheduler.main --run-now      # разовый прогон scheduler
```

**Ключевые переменные окружения:** `DATABASE_URL`, `API_KEY`, `LLM_ENABLED`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_CA_BUNDLE`, `HH_SOURCE`, `HH_API_FALLBACK_ENABLED`, `HH_BACKFILL_ITEMS_PER_PAGE`, `HH_BACKFILL_RESULT_CAP`, `SCHEDULER_CRON_HOUR/MINUTE`, `SCHEDULER_TIMEZONE`, `SCHEDULER_MAX_PAGES`. Полный список — в [`.env.example`](../.env.example) и корневом [`README.md`](../README.md).

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-06-07 | **Phase 8 — Backfill + хотфикс scheduler #2.** Добавлен компонент Backfill (массовое первичное наполнение с рекурсивной сегментацией по датам, FR-48–FR-51, NFR-33–NFR-34). Зафиксирован хотфикс scheduler #2 (asyncio.run + Event.wait + graceful shutdown, контейнер стабилен). Обновлены: 02-architecture (§2.3b, §2.4, AD-13/AD-14), 01-requirements (FR-48–51, NFR-33–34), 03-data-model (meta JSONB), 05-tech-stack (настройки backfill, нюанс DD.MM.YYYY), 06-api-contract (CLI-операции, ingestion/status meta), 07-roadmap (Phase 8 Completed, хотфиксы, known-issues), 00-overview, README.md. 227 тестов зелёные. |
| 2026-06 | **Финализация MVP.** Спецификация синхронизирована с фактической реализацией всех фаз 0–7: HTML-парсинг primary, scheduler (APScheduler + overlap-protection + хотфикс пустых env), метрики M1–M5 (on-the-fly + готовые snapshots), LLM-инсайты и анализатор резюме (санитизация PII, ФИО в любом порядке), TLS `LLM_CA_BUNDLE`. Зафиксированы фактические эндпоинты, миграции 0001–0003, известные ограничения и дальнейшие шаги. |
