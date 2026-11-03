from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field


EventSource = Literal["telegram", "crm", "webform", "email"]
IntentType = Literal["sales", "support", "billing", "spam"]
UrgencyLevel = Literal["low", "medium", "high"]


class InboundWebhookEvent(BaseModel):
    event_id: str = Field(..., min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9_.:-]+$")
    source: EventSource
    client_id: str = Field(..., min_length=1, max_length=80)
    text: str = Field(..., min_length=1, max_length=8000)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TriageDecision(BaseModel):
    intent: IntentType
    urgency: UrgencyLevel
    sanitized_summary: str = Field(..., max_length=400)
    route_to_queue: str
    suggested_reply: str = Field(..., max_length=1000)


class WorkflowResponse(BaseModel):
    event_id: str
    status: Literal["processed", "duplicate_ignored", "blocked_injection"]
    triage: Optional[TriageDecision] = None
    pii_masked: bool = False
    latency_ms: float


class MetricsSnapshot(BaseModel):
    total_received: int
    processed: int
    duplicates_ignored: int
    injections_blocked: int
    avg_latency_ms: float
