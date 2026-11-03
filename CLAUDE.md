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
