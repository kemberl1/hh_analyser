# 06 — Контракт REST API (API Contract)

> Базовый префикс: `/api/v1`. Формат — JSON. Спецификация OpenAPI генерируется автоматически (FastAPI) на `/docs` и `/openapi.json`.
> Метрики отдаются из предрассчитанных снапшотов (см. [`04-metrics.md`](04-metrics.md)).

---

## 1. Общие соглашения

### 1.1. Общие query-параметры (фильтры)

| Параметр | Тип | Значения | По умолчанию | Описание |
|----------|-----|----------|--------------|----------|
| `period` | enum | `day` `week` `month` `year` | `month` | Гранулярность периода |
| `date_from` | date | ISO `YYYY-MM-DD` | — | Начало диапазона (по `published_at`) |
| `date_to` | date | ISO `YYYY-MM-DD` | сегодня | Конец диапазона |
| `grade` | enum | `junior` `middle` `senior` `all` | `all` | Грейд |
| `currency` | enum | `RUB` `USD` `EUR` | `RUB` | Базовая валюта вывода |
| `salary_basis` | enum | `net` `gross` | `net` | Базис зарплаты |

> Если задан `date_from`/`date_to` — данные агрегируются за диапазон с гранулярностью `period`. Без диапазона — берётся последний доступный период.

### 1.2. Формат ошибок

```json
{
  "error": {
    "code": "INVALID_PERIOD",
    "message": "period must be one of day, week, month, year",
    "details": { "param": "period" }
  }
}
```

| HTTP | Когда |
|------|-------|
| 200 | Успех |
| 400 | Ошибка валидации параметров |
| 404 | Ресурс не найден |
| 422 | Невалидное тело/параметры (Pydantic) |
| 503 | Данные ещё не готовы (нет успешных прогонов) |

### 1.3. Конверт ответа метрик

```json
{
  "meta": {
    "period": "month",
    "date_from": "2026-05-01",
    "date_to": "2026-05-31",
    "grade": "all",
    "currency": "RUB",
    "salary_basis": "net",
    "computed_at": "2026-06-01T03:15:00Z",
    "low_confidence": false,
    "sample_size": 1843
  },
  "data": { }
}
```

---

## 2. Служебные эндпоинты

### 2.1. `GET /api/v1/health`

Проверка живости.

```json
{ "status": "ok" }
```

### 2.2. `GET /api/v1/ingestion/status`

Статус последнего прогона сбора (FR-25, NFR-20).

```json
{
  "last_run": {
    "id": 412,
    "started_at": "2026-06-06T03:00:00Z",
    "finished_at": "2026-06-06T03:14:22Z",
    "status": "success",
    "found_total": 2150,
    "created_count": 180,
    "updated_count": 1960,
    "error_count": 10,
    "html_fallback_count": 4
  },
  "data_freshness_hours": 12.1
}
```

---

## 3. Эндпоинты метрик

### 3.1. `GET /api/v1/metrics/salary`

Зарплатные метрики (группа M1).

**Query:** общие фильтры (§1.1).

**Пример ответа:**

```json
{
  "meta": {
    "period": "month", "date_from": "2026-05-01", "date_to": "2026-05-31",
    "grade": "middle", "currency": "RUB", "salary_basis": "net",
    "computed_at": "2026-06-01T03:15:00Z", "low_confidence": false, "sample_size": 640
  },
  "data": {
    "median": 220000,
    "min": 90000,
    "max": 450000,
    "mean": 228500,
    "percentiles": { "p10": 130000, "p25": 170000, "p50": 220000, "p75": 280000, "p90": 340000 },
    "range_avg": { "from": 195000, "to": 255000 },
    "salary_disclosure_rate": 0.62,
    "currency": "RUB",
    "salary_basis": "net"
  }
}
```

### 3.2. `GET /api/v1/metrics/salary/timeseries`

Временной ряд медианной зарплаты (M4.2).

```json
{
  "meta": { "period": "month", "grade": "all", "currency": "RUB", "salary_basis": "net" },
  "data": {
    "points": [
      { "period_start": "2026-03-01", "median": 205000, "p25": 160000, "p75": 265000, "count": 1750 },
      { "period_start": "2026-04-01", "median": 212000, "p25": 165000, "p75": 270000, "count": 1820 },
      { "period_start": "2026-05-01", "median": 220000, "p25": 170000, "p75": 280000, "count": 1843 }
    ]
  }
}
```

### 3.3. `GET /api/v1/metrics/skills`

Рейтинг навыков (группа M2). Дополнительный query: `limit` (default 20).

```json
{
  "meta": { "period": "month", "date_from": "2026-05-01", "date_to": "2026-05-31", "grade": "junior", "sample_size": 410 },
  "data": {
    "skills": [
      { "skill": "React", "canonical": "react", "count": 320, "share": 0.78 },
      { "skill": "TypeScript", "canonical": "typescript", "count": 290, "share": 0.71 },
      { "skill": "JavaScript", "canonical": "javascript", "count": 280, "share": 0.68 },
      { "skill": "HTML", "canonical": "html", "count": 250, "share": 0.61 },
      { "skill": "CSS", "canonical": "css", "count": 245, "share": 0.60 }
    ]
  }
}
```

### 3.4. `GET /api/v1/metrics/skills/cooccurrence`

Топ-связки навыков (M5.4). Query: `limit`.

```json
{
  "meta": { "period": "month", "grade": "all" },
  "data": {
    "pairs": [
      { "a": "React", "b": "TypeScript", "count": 410, "share": 0.55 },
      { "a": "React", "b": "Redux", "count": 230, "share": 0.31 }
    ]
  }
}
```

### 3.5. `GET /api/v1/metrics/employers`

Топ работодателей (группа M3). Query: `limit`.

```json
{
  "meta": { "period": "month", "date_from": "2026-05-01", "date_to": "2026-05-31", "grade": "all" },
  "data": {
    "employers": [
      { "employer_id": 1234, "name": "Yandex", "count": 85, "share": 0.046 },
      { "employer_id": 5678, "name": "Sber", "count": 70, "share": 0.038 }
    ],
    "top10_concentration": 0.27
  }
}
```

### 3.6. `GET /api/v1/metrics/demand`

Динамика спроса — кол-во вакансий по периодам и рост/падение (M4.1, M4.3).

```json
{
  "meta": { "period": "week", "grade": "all" },
  "data": {
    "points": [
      { "period_start": "2026-05-04", "count": 430, "growth": 0.05 },
      { "period_start": "2026-05-11", "count": 455, "growth": 0.058 },
      { "period_start": "2026-05-18", "count": 410, "growth": -0.099 }
    ]
  }
}
```

### 3.7. `GET /api/v1/metrics/distribution`

Распределения (M5.1–M5.3). Query: `by` = `grade` | `format` | `experience`.

```json
{
  "meta": { "period": "month", "by": "grade" },
  "data": {
    "distribution": [
      { "key": "junior", "label": "Junior", "count": 410, "share": 0.22 },
      { "key": "middle", "label": "Middle", "count": 820, "share": 0.45 },
      { "key": "senior", "label": "Senior", "count": 613, "share": 0.33 }
    ]
  }
}
```

### 3.8. `GET /api/v1/metrics/overview`

Сводка для главного дашборда (агрегирует ключевые метрики в одном ответе — для производительности фронта).

```json
{
  "meta": { "period": "month", "grade": "all", "currency": "RUB", "salary_basis": "net", "sample_size": 1843 },
  "data": {
    "salary": { "median": 215000, "p25": 165000, "p75": 275000 },
    "total_vacancies": 1843,
    "salary_disclosure_rate": 0.60,
    "top_skills": [ { "skill": "React", "share": 0.74 }, { "skill": "TypeScript", "share": 0.69 } ],
    "top_employers": [ { "name": "Yandex", "count": 85 } ],
    "grade_distribution": [ { "key": "junior", "share": 0.22 }, { "key": "middle", "share": 0.45 }, { "key": "senior", "share": 0.33 } ],
    "demand_growth_mom": 0.04
  }
}
```

---

## 4. Списочные эндпоинты (опционально, FR-26)

### 4.1. `GET /api/v1/vacancies`

Список вакансий с пагинацией (для drill-down / отладки).

**Query:** общие фильтры + `skill`, `employer_id`, `page` (default 1), `page_size` (default 50, max 200), `sort` (`published_at_desc` default).

```json
{
  "meta": { "page": 1, "page_size": 50, "total": 1843 },
  "data": [
    {
      "hh_vacancy_id": 99887766,
      "title": "Frontend разработчик (React)",
      "employer": { "id": 1234, "name": "Yandex" },
      "grade": "middle",
      "salary": { "from": 200000, "to": 280000, "currency": "RUB", "gross": false, "point_estimate_rub_net": 240000 },
      "employment_format": "remote",
      "published_at": "2026-05-20T09:30:00Z",
      "url": "https://hh.ru/vacancy/99887766"
    }
  ]
}
```

### 4.2. `GET /api/v1/skills`

Справочник канонических навыков (для автодополнения фильтров).

### 4.3. `GET /api/v1/employers`

Справочник работодателей с числом вакансий.

---

## 5. Эндпоинты LLM (поздние фазы — проектно)

> Реализуются на Phase 6–7; здесь зафиксирован контракт-набросок.

### 5.1. `GET /api/v1/insights/market` (Phase 6)

LLM-сгенерированный текстовый анализ рынка по агрегатам.

```json
{
  "meta": { "period": "month", "grade": "all", "model": "x5-airun-medium", "generated_at": "2026-06-06T04:00:00Z" },
  "data": {
    "summary": "Спрос на Frontend стабилен; медиана Middle выросла на 4 процента MoM...",
    "highlights": [ "React и TypeScript — обязательный стек", "Растёт доля remote" ],
    "based_on": { "sample_size": 1843, "snapshot_ids": [1201, 1202] }
  }
}
```

### 5.2. `POST /api/v1/resume/analyze` (Phase 7)

Анализ резюме (профпригодность). Тело — текст резюме или файл (multipart). PII санитизируется перед отправкой в LLM (NFR-16).

**Request (application/json):**

```json
{ "resume_text": "...", "target_grade": "middle", "consent_store": false }
```

**Response:**

```json
{
  "meta": { "model": "x5-airun-medium", "embedding_model": "x5-airun-embed-4b", "analyzed_at": "2026-06-06T10:00:00Z" },
  "data": {
    "market_fit_score": 0.72,
    "passes_keyword_filters": true,
    "matched_skills": [ "React", "TypeScript", "Redux" ],
    "missing_in_demand_skills": [ "Next.js", "Testing" ],
    "recommendations": [ "Добавить опыт с Next.js", "Указать инструменты тестирования" ]
  }
}
```

---

## 6. Сводная таблица эндпоинтов

| Метод | Путь | Назначение | Фаза |
|-------|------|------------|------|
| GET | `/api/v1/health` | живость | 1 |
| GET | `/api/v1/ingestion/status` | статус сбора | 3 |
| GET | `/api/v1/metrics/salary` | зарплатные метрики | 4 |
| GET | `/api/v1/metrics/salary/timeseries` | ряд медианы | 4 |
| GET | `/api/v1/metrics/skills` | рейтинг навыков | 4 |
| GET | `/api/v1/metrics/skills/cooccurrence` | связки навыков | 4 |
| GET | `/api/v1/metrics/employers` | топ работодателей | 4 |
| GET | `/api/v1/metrics/demand` | динамика спроса | 4 |
| GET | `/api/v1/metrics/distribution` | распределения | 4 |
| GET | `/api/v1/metrics/overview` | сводка дашборда | 4 |
| GET | `/api/v1/vacancies` | список вакансий | 4 |
| GET | `/api/v1/skills` | справочник навыков | 4 |
| GET | `/api/v1/employers` | справочник работодателей | 4 |
| GET | `/api/v1/insights/market` | LLM-анализ рынка | 6 |
| POST | `/api/v1/resume/analyze` | анализ резюме | 7 |
