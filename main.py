import os
from pathlib import Path
from fastapi import Depends, FastAPI, Header, HTTPException

from app.schemas import InboundWebhookEvent, MetricsSnapshot, WorkflowResponse
from app.security import SlidingWindowRateLimiter
from app.workflow import WebhookWorkflowEngine


def create_app(
    db_path: Path | None = None,
    api_key: str | None = None,
    rate_limit_per_min: int = 30,
) -> FastAPI:
    app = FastAPI(
        title="AI Webhook Workflow Starter",
        description=(
            "Production-ready FastAPI template for inbound CRM / Telegram AI workflows: "
            "idempotency, PII masking, prompt-injection guardrails, rate limiting, and metrics."
        ),
        version="1.0.0",
    )

    resolved_db = db_path or Path(os.getenv("WORKFLOW_DB_PATH", "./data/events.db"))
    expected_key = api_key if api_key is not None else os.getenv("WEBHOOK_API_KEY", "dev-webhook-key")

    engine = WebhookWorkflowEngine(resolved_db)
    limiter = SlidingWindowRateLimiter(max_requests=rate_limit_per_min, window_seconds=60)

    def require_key(x_api_key: str | None = Header(default=None)) -> None:
        if not x_api_key or x_api_key != expected_key:
            raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "ai-webhook-workflow-starter"}

    @app.post(
        "/v1/webhooks/inbound",
        response_model=WorkflowResponse,
        dependencies=[Depends(require_key)],
    )
    async def inbound_webhook(event: InboundWebhookEvent):
        if not limiter.allow(event.client_id):
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded for client_id",
            )
        return await engine.process_event(event)

    @app.get("/v1/events/{event_id}", dependencies=[Depends(require_key)])
    async def get_event_audit(event_id: str):
        record = engine.get_event(event_id)
        if not record:
            raise HTTPException(status_code=404, detail="Event not found")
        return record

    @app.get(
        "/v1/metrics",
        response_model=MetricsSnapshot,
        dependencies=[Depends(require_key)],
    )
    async def metrics():
        return engine.get_metrics()

    return app


app = create_app()
