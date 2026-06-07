# HH Analyser — Техническая спецификация

> **Статус:** MVP реализован (все фазы 0–7 завершены и проверены на живых сервисах). Спецификация синхронизирована с фактической реализацией. 205 бэкенд-тестов зелёные.

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
- **Relevance Filtering:** нерелевантные вакансии (Fullstack, Backend, PM, QA и т.п.) отсеиваются и не попадают в БД; словари ключевых/стоп-слов конфигурируемы.
- Учёт статистики по дате публикации `published_at` (не перезаписывается при upsert).
- Идемпотентный сбор (dedup по `hh_vacancy_id`).
- Механизм предрасчёта метрик в `snapshots` готов; в MVP эндпоинты считают on-the-fly.
- Заменяемый LLM-провайдер через абстрактный адаптер (X5 CoPilot); TLS-верификация с кастомным `LLM_CA_BUNDLE`.
- Санитизация PII резюме перед LLM; резюме не персистится.
- Итеративная поставка: 7 независимо проверяемых фаз (все завершены).

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

# 4. Сбор данных и снапшоты (CLI)
python -m app.cli ingest [--max-pages N]   # запуск пайплайна сбора
python -m app.cli seed                      # сид словарей relevance_terms
python -m app.cli rebuild-snapshots         # пересчёт предрассчитанных метрик
python -m app.scheduler.main --run-now      # разовый прогон scheduler
```

**Ключевые переменные окружения:** `DATABASE_URL`, `API_KEY`, `LLM_ENABLED`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_CA_BUNDLE`, `HH_SOURCE`, `HH_API_FALLBACK_ENABLED`, `SCHEDULER_CRON_HOUR/MINUTE`, `SCHEDULER_TIMEZONE`, `SCHEDULER_MAX_PAGES`. Полный список — в [`.env.example`](../.env.example) и корневом [`README.md`](../README.md).

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-06 | **Финализация MVP.** Спецификация синхронизирована с фактической реализацией всех фаз 0–7: HTML-парсинг primary, scheduler (APScheduler + overlap-protection + хотфикс пустых env), метрики M1–M5 (on-the-fly + готовые snapshots), LLM-инсайты и анализатор резюме (санитизация PII, ФИО в любом порядке), TLS `LLM_CA_BUNDLE`. Зафиксированы фактические эндпоинты, миграции 0001–0003, известные ограничения и дальнейшие шаги. |
