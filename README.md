[Uploading app…]()
WEBHOOK_API_KEY=replace-with-strong-secret
WORKFLOW_DB_PATH=./data/events.db

__pycache__/
*.py[cod]
.pytest_cache/
.venv/
venv/
.env
data/

# CLAUDE.md — Project Rules

## Purpose
Готовый шаблон бэкенда для заказных интеграций (Telegram / CRM / Webforms → AI-триаж и маршрутизация лидов).

## Guardrails & Invariants
1. **Idempotency:** каждый входящий `event_id` обрабатывается ровно один раз; повторные вебхуки возвращают `status="duplicate_ignored"`.
2. **Security:** до отправки текста в классификатор/LLM выполняется фильтрация `Prompt Injection` и маскирование номеров карт и секретов (`mask_sensitive_pii`).
3. **Budget Protection:** скользящий лимит запросов (`SlidingWindowRateLimiter`) по `client_id` защищает баланс токенов от спам-атак (`429`).

## Commands
- Прогон автотестов: `pytest -v`
- Запуск локально: `uvicorn app.main:app --reload --port 8010`
- Запуск в Docker: `docker compose up --build -d`

services:
  webhook-workflow:
    build: .
    ports:
      - "8010:8010"
    environment:
      - WORKFLOW_DB_PATH=/srv/app/data/events.db
      - WEBHOOK_API_KEY=${WEBHOOK_API_KEY:-change-me-in-prod}
    volumes:
      - workflow_data:/srv/app/data
    restart: unless-stopped

volumes:
  workflow_data:

FROM python:3.12-slim

WORKDIR /srv/app

RUN adduser --disabled-password --gecos "" appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN mkdir -p /srv/app/data && chown -R appuser:appuser /srv/app
USER appuser

EXPOSE 8010
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]

[project]
name = "ai-webhook-workflow-starter"
version = "1.0.0"
description = "FastAPI inbound AI webhook & CRM triage starter with idempotency, PII masking, prompt-injection defense, and metrics"
requires-python = ">=3.11"

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]

# AI Webhook Workflow Starter

Базовый **FastAPI**-шаблон для быстрого запуска клиентских AI-воркфлоу (обработка обращений из Telegram, веб-форм и CRM с маршрутизацией по очередям, защитой данных и метриками).

## Что уже заложено в шаблон

- **Строгая идемпотентность (`event_id`):** защита от повторных вебхуков Telegram / AmoCRM / Битрикс24 — дубликаты не вызывают повторную генерацию и не плодят одинаковые сделки.
- **Инфобез до вызова LLM:**
  - автоматическое маскирование номеров банковских карт и случайно вставленных ключей (`[CARD_MASKED]`, `[SECRET_MASKED]`);
  - базовый фильтр попыток `Prompt Injection` (`blocked_injection`);
  - скользящий `Rate Limiter` на каждого `client_id` (`429 Too Many Requests`), чтобы спам-боты не сжигали бюджет токенов.
- **Структурированный выход (`Pydantic v2`):** интент (`sales | support | billing | spam`), срочность, очередь маршрутизации и черновик ответа.
- **Встроенные операционные метрики (`GET /v1/metrics`):** число обработанных событий, отсечённых дублей, заблокированных инъекций и средний `latency_ms`.

---

## Структура

```text
ai-webhook-workflow-starter/
├── app/
│   ├── main.py         # Эндпоинты вебхуков, аудита и метрик
│   ├── schemas.py      # Pydantic v2 контракты входов и выходов
│   ├── security.py     # Маскирование PII, фильтр инъекций, HMAC и Rate Limit
│   └── workflow.py     # Идемпотентный движок обработки и SQLite аудит-лог
├── tests/
│   └── test_workflow.py # Автотесты (PII, дубли, инъекции, 401, 429)
├── CLAUDE.md
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Запуск и тесты

```bash
pip install -r requirements.txt
pytest -v
uvicorn app.main:app --reload --port 8010
```

Через Docker Compose:
```bash
WEBHOOK_API_KEY=super-secret docker compose up --build -d
```

fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.8.0
pytest>=8.2.0
httpx>=0.27.0
