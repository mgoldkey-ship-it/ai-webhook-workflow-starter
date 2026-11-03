import json
import sqlite3
import time
from pathlib import Path
from typing import Optional, Protocol

from app.schemas import InboundWebhookEvent, MetricsSnapshot, TriageDecision, WorkflowResponse
from app.security import detect_prompt_injection, mask_sensitive_pii


class TriageClassifier(Protocol):
    async def classify(self, clean_text: str, source: str) -> TriageDecision:
        ...


class RuleFallbackClassifier:
    """
    Deterministic classifier used when LLM_API_KEY is not configured or for local testing.
    In production, swap or wrap with OpenAI / Anthropic Structured Outputs adapter.
    """

    async def classify(self, clean_text: str, source: str) -> TriageDecision:
        low = clean_text.lower()
        if any(w in low for w in ("счет", "счёт", "оплат", "возврат", "чек", "invoice", "refund")):
            intent, queue, urgency = "billing", "crm_billing_pipeline", "high"
            reply = "Передали ваш вопрос по оплате в финансовый отдел — вернёмся с ответом в ближайшее время."
        elif any(w in low for w in ("купить", "цен", "заказ", "подключ", "тариф", "кп", "price")):
            intent, queue, urgency = "sales", "crm_sales_leads", "medium"
            reply = "Спасибо за обращение! Подготовим расчёт под вашу задачу и свяжемся с вами."
        elif any(w in low for w in ("казино", "крипто сигналы", "спам", "free money")):
            intent, queue, urgency = "spam", "archive_spam", "low"
            reply = "Обращение отклонено автоматическим фильтром."
        else:
            intent, queue = "support", "crm_support_l1"
            urgency = "high" if any(w in low for w in ("срочно", "не работает", "упал", "ошибка")) else "medium"
            reply = "Приняли обращение в техподдержку, уже проверяем детали."

        summary = clean_text[:220] + ("..." if len(clean_text) > 220 else "")
        return TriageDecision(
            intent=intent,
            urgency=urgency,
            sanitized_summary=summary,
            route_to_queue=queue,
            suggested_reply=reply,
        )


class WebhookWorkflowEngine:
    """
    Idempotent webhook processor with SQLite audit log, PII masking,
    prompt-injection guardrails, and latency/quality metrics.
    """

    def __init__(self, db_path: Path, classifier: Optional[TriageClassifier] = None) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.classifier = classifier or RuleFallbackClassifier()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS webhook_events (
                    event_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    pii_masked INTEGER NOT NULL DEFAULT 0,
                    triage_json TEXT,
                    latency_ms REAL NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS counters (
                    name TEXT PRIMARY KEY,
                    val INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO counters (name, val) VALUES ('duplicates_ignored', 0)"
            )

    def get_event(self, event_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM webhook_events WHERE event_id = ?", (event_id,)
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            if data.get("triage_json"):
                data["triage"] = json.loads(data.pop("triage_json"))
            return data

    async def process_event(self, event: InboundWebhookEvent) -> WorkflowResponse:
        t0 = time.perf_counter()

        # 1. Idempotency check
        existing = self.get_event(event.event_id)
        if existing is not None:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE counters SET val = val + 1 WHERE name = 'duplicates_ignored'"
                )
            elapsed = round((time.perf_counter() - t0) * 1000, 2)
            triage_obj = (
                TriageDecision(**existing["triage"]) if existing.get("triage") else None
            )
            return WorkflowResponse(
                event_id=event.event_id,
                status="duplicate_ignored",
                triage=triage_obj,
                pii_masked=bool(existing["pii_masked"]),
                latency_ms=elapsed,
            )

        # 2. Prompt injection guardrail
        if detect_prompt_injection(event.text):
            elapsed = round((time.perf_counter() - t0) * 1000, 2)
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO webhook_events
                    (event_id, source, client_id, status, pii_masked, triage_json, latency_ms, created_at)
                    VALUES (?, ?, ?, 'blocked_injection', 0, NULL, ?, ?)
                    """,
                    (event.event_id, event.source, event.client_id, elapsed, time.time()),
                )
            return WorkflowResponse(
                event_id=event.event_id,
                status="blocked_injection",
                triage=None,
                pii_masked=False,
                latency_ms=elapsed,
            )

        # 3. Mask sensitive PII before classification / LLM call
        clean_text, was_masked = mask_sensitive_pii(event.text)

        # 4. Run structured AI / workflow classification
        decision = await self.classifier.classify(clean_text, event.source)
        elapsed = round((time.perf_counter() - t0) * 1000, 2)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO webhook_events
                (event_id, source, client_id, status, pii_masked, triage_json, latency_ms, created_at)
                VALUES (?, ?, ?, 'processed', ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.source,
                    event.client_id,
                    int(was_masked),
                    json.dumps(decision.model_dump(), ensure_ascii=False),
                    elapsed,
                    time.time(),
                ),
            )

        return WorkflowResponse(
            event_id=event.event_id,
            status="processed",
            triage=decision,
            pii_masked=was_masked,
            latency_ms=elapsed,
        )

    def get_metrics(self) -> MetricsSnapshot:
        with self._connect() as conn:
            proc = conn.execute(
                "SELECT COUNT(*) FROM webhook_events WHERE status = 'processed'"
            ).fetchone()[0]
            blocked = conn.execute(
                "SELECT COUNT(*) FROM webhook_events WHERE status = 'blocked_injection'"
            ).fetchone()[0]
            dups = conn.execute(
                "SELECT val FROM counters WHERE name = 'duplicates_ignored'"
            ).fetchone()[0]
            avg_lat = conn.execute(
                "SELECT COALESCE(AVG(latency_ms), 0.0) FROM webhook_events"
            ).fetchone()[0]

        total = proc + blocked + dups
        return MetricsSnapshot(
            total_received=total,
            processed=proc,
            duplicates_ignored=dups,
            injections_blocked=blocked,
            avg_latency_ms=round(float(avg_lat), 2),
        )
