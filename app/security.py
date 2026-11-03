import hashlib
import hmac
import re
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple


# Common prompt-injection attempts trying to hijack system instructions or exfiltrate secrets
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"(reveal|print|show)\s+(your\s+)?(system\s+prompt|api\s*key|secret)", re.IGNORECASE),
    re.compile(r"забудь\s+(все\s+)?(предыдущие\s+)?инструкции", re.IGNORECASE),
    re.compile(r"(покажи|выведи)\s+(системный\s+промпт|ключи|пароли)", re.IGNORECASE),
]

# Card numbers (16 digits) and secret-like tokens
CARD_RE = re.compile(r"\b(?:\d[ -]*?){16}\b")
SECRET_TOKEN_RE = re.compile(r"\b(sk-[a-zA-Z0-9_-]{16,})\b")


def detect_prompt_injection(text: str) -> bool:
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            return True
    return False


def mask_sensitive_pii(text: str) -> Tuple[str, bool]:
    """Masks payment card numbers and leaked API tokens before sending text to external LLMs."""
    masked = CARD_RE.sub("[CARD_MASKED]", text)
    masked = SECRET_TOKEN_RE.sub("[SECRET_MASKED]", masked)
    return masked, (masked != text)


def verify_hmac_signature(raw_body: bytes, signature_header: str, secret: str) -> bool:
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=").strip()
    return hmac.compare_digest(expected, provided)


class SlidingWindowRateLimiter:
    """Per-client sliding window rate limiter to protect LLM token budget."""

    def __init__(self, max_requests: int = 20, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, client_id: str) -> bool:
        now = time.monotonic()
        q = self._hits[client_id]
        cutoff = now - self.window_seconds
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= self.max_requests:
            return False
        q.append(now)
        return True
