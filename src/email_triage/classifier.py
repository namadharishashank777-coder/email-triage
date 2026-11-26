"""Email classification backends using Gemini API, Antigravity SDK, or mock rules."""

import asyncio
import json
import re
import time
from typing import Any, Protocol

from email_triage.models import Category, EmailMessage, TriageResult
from email_triage.parser import parse_triage_json

SYSTEM_INSTRUCTIONS = """You are an Email Triage Agent.
Classify each incoming email into EXACTLY ONE of these categories:
- "Urgent Support"
- "Sales Lead"
- "Billing/Invoice"
- "Low Priority/Newsletter"

Assign an integer priority score from 1 (lowest) to 5 (highest):
- 5: Critical outage, security incident, or immediate blocker
- 4: High-urgency customer issue or hot enterprise sales inquiry
- 3: Standard support, qualified lead, or time-sensitive invoice
- 2: Routine billing receipt or low-urgency follow-up
- 1: Newsletters, digests, or promotional mail

Return ONLY valid JSON matching this schema:
{
  "category": "Urgent Support | Sales Lead | Billing/Invoice | Low Priority/Newsletter",
  "priority": 1-5,
  "action_required": "Short summary of the next human action",
  "suggested_reply": "Polite, context-aware draft reply for Urgent Support or Sales Lead; empty string if no reply is needed"
}"""


class EmailClassifier(Protocol):
    """Protocol implemented by all email classification backends."""

    def classify(self, email: EmailMessage) -> TriageResult:
        """Classify an email and return structured triage metadata."""
        ...


def build_triage_prompt(email: EmailMessage) -> str:
    """Format an email and its prior thread history into a classification prompt."""
    sections = [
        f"Sender: {email.sender}",
        f"Subject: {email.subject}",
    ]
    if email.received_at:
        sections.append(f"Received: {email.received_at}")

    if email.thread_context:
        thread_lines = ["Thread Context (earliest to most recent):"]
        for idx, msg in enumerate(email.thread_context, start=1):
            thread_lines.append(
                f"  [{idx}] From: {msg.sender} | Subject: {msg.subject}\n"
                f"      {msg.body.strip()}"
            )
        sections.append("\n".join(thread_lines))

    sections.append(f"Latest Email Body:\n{email.body.strip()}")
    return "\n\n".join(sections)


class GeminiClassifier:
    """Classifier backed by the Google Gemini API (`google-genai`)."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.6-flash",
        client: Any = None,
        max_retries: int = 3,
        retry_delay: float = 1.5,
    ) -> None:
        if client is None and not api_key:
            raise ValueError("GEMINI_API_KEY is required for GeminiClassifier.")
        self.model = model
        self.max_retries = max(1, max_retries)
        self.retry_delay = max(0.0, retry_delay)
        if client is not None:
            self._client = client
        else:
            from google import genai
            from google.genai import types

            self._client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=30_000),
            )

    def classify(self, email: EmailMessage) -> TriageResult:
        """Classify an email with Gemini structured JSON output."""
        from google.genai import errors as genai_errors
        from google.genai import types

        prompt = f"{SYSTEM_INSTRUCTIONS}\n\n---\n\n{build_triage_prompt(email)}"
        config = types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
            response_schema=TriageResult,
        )

        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = self._client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )
                raw_text = getattr(response, "text", "") or ""
                return parse_triage_json(raw_text)
            except genai_errors.APIError as exc:
                last_exc = exc
                status_code = getattr(exc, "code", None)
                if status_code not in {429, 500, 502, 503, 504} or attempt == self.max_retries - 1:
                    raise
                if self.retry_delay > 0:
                    time.sleep(self.retry_delay * (2**attempt))

        assert last_exc is not None  # pragma: no cover
        raise last_exc


class AntigravityClassifier:
    """Classifier backed by the Google Antigravity Python SDK (`google-antigravity`)."""

    def __init__(self, system_instructions: str = SYSTEM_INSTRUCTIONS) -> None:
        self.system_instructions = system_instructions

    async def _classify_async(self, email: EmailMessage) -> TriageResult:
        try:
            from google.antigravity import Agent, LocalAgentConfig
        except ImportError as exc:
            raise RuntimeError(
                "google-antigravity is not installed. Install with: "
                "pip install google-antigravity"
            ) from exc

        config = LocalAgentConfig(system_instructions=self.system_instructions)
        prompt = build_triage_prompt(email)
        chunks: list[str] = []
        async with Agent(config) as agent:
            response = await agent.chat(prompt)
            async for token in response:
                chunks.append(token)
        return parse_triage_json("".join(chunks))

    def classify(self, email: EmailMessage) -> TriageResult:
        """Run the async Antigravity Agent classification synchronously."""
        return asyncio.run(self._classify_async(email))


class MockClassifier:
    """Deterministic offline classifier for dry-run testing without API credentials."""

    _URGENT_RE = re.compile(
        r"\b(outage|down|500|urgent|locked out|blocker|sev1)\b", re.IGNORECASE
    )
    _SALES_RE = re.compile(
        r"\b(pricing|demo|enterprise|seats|quote|contract|trial)\b", re.IGNORECASE
    )
    _BILLING_RE = re.compile(
        r"\b(invoice|billing|receipt|payment|remittance|statement)\b", re.IGNORECASE
    )

    def classify(self, email: EmailMessage) -> TriageResult:
        """Classify using deterministic keyword rules and route through JSON parsing."""
        combined = " ".join(
            [
                email.subject,
                email.body,
                *(msg.body for msg in email.thread_context),
            ]
        )

        if self._URGENT_RE.search(combined):
            payload = {
                "category": Category.URGENT_SUPPORT.value,
                "priority": 5,
                "action_required": "Escalate to on-call support and update customer immediately.",
                "suggested_reply": (
                    f"Hi,\n\nThanks for flagging this right away regarding '{email.subject}'. "
                    "Our engineering support team is investigating the issue with top priority "
                    "and will send you a status update shortly.\n\nBest regards,\nSupport Team"
                ),
            }
        elif self._SALES_RE.search(combined):
            payload = {
                "category": Category.SALES_LEAD.value,
                "priority": 4,
                "action_required": "Assign to account executive and schedule discovery call.",
                "suggested_reply": (
                    f"Hi,\n\nThank you for reaching out about '{email.subject}'. "
                    "We would love to share tailored pricing and walk through your requirements. "
                    "Are you available for a brief 20-minute call this week?\n\nBest regards,\nSales Team"
                ),
            }
        elif self._BILLING_RE.search(combined):
            payload = {
                "category": Category.BILLING_INVOICE.value,
                "priority": 2,
                "action_required": "Log invoice/receipt in accounting records; no customer reply needed.",
                "suggested_reply": "",
            }
        else:
            payload = {
                "category": Category.LOW_PRIORITY_NEWSLETTER.value,
                "priority": 1,
                "action_required": "Archive or review at leisure.",
                "suggested_reply": "",
            }

        return parse_triage_json(json.dumps(payload))
