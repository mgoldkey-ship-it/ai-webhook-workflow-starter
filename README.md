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
