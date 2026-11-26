"""Unit tests for email classification prompts and classifier backends."""

import json
from types import SimpleNamespace

import pytest

from email_triage.classifier import (
    GeminiClassifier,
    MockClassifier,
    build_triage_prompt,
)
from email_triage.mock_data import SAMPLE_EMAILS
from email_triage.models import Category, EmailMessage, ThreadMessage


class _FakeGeminiModels:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.calls: list[dict[str, object]] = []

    def generate_content(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(text=self.response_text)


class _FakeGeminiClient:
    def __init__(self, response_text: str) -> None:
        self.models = _FakeGeminiModels(response_text)


def test_build_triage_prompt_includes_thread_context() -> None:
    email = EmailMessage(
        id="m-2",
        thread_id="t-1",
        sender="alice@example.com",
        subject="Re: Checkout outage",
        body="Still failing with 500 errors.",
        thread_context=[
            ThreadMessage(
                sender="alice@example.com",
                subject="Checkout outage",
                body="Started seeing timeouts 10 minutes ago.",
            )
        ],
    )
    prompt = build_triage_prompt(email)
    assert "Sender: alice@example.com" in prompt
    assert "Subject: Re: Checkout outage" in prompt
    assert "Started seeing timeouts 10 minutes ago." in prompt
    assert "Still failing with 500 errors." in prompt


def test_gemini_classifier_parses_structured_response() -> None:
    fake_payload = json.dumps(
        {
            "category": "Sales Lead",
            "priority": 4,
            "action_required": "Send enterprise pricing deck and propose call.",
            "suggested_reply": "Thanks for reaching out! Let's schedule a call.",
        }
    )
    fake_client = _FakeGeminiClient(fake_payload)
    classifier = GeminiClassifier(
        api_key="test-key",
        model="gemini-3.6-flash",
        client=fake_client,
    )

    result = classifier.classify(SAMPLE_EMAILS[1])
    assert result.category is Category.SALES_LEAD
    assert result.priority == 4
    assert len(fake_client.models.calls) == 1
    assert fake_client.models.calls[0]["model"] == "gemini-3.6-flash"


def test_gemini_classifier_requires_api_key_when_no_client() -> None:
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        GeminiClassifier(api_key="")


def test_gemini_classifier_retries_on_transient_503() -> None:
    from google.genai import errors as genai_errors

    fake_payload = json.dumps(
        {
            "category": "Urgent Support",
            "priority": 5,
            "action_required": "Escalate immediately.",
            "suggested_reply": "We are on it right now.",
        }
    )

    class _FlakyModels:
        def __init__(self) -> None:
            self.attempts = 0

        def generate_content(self, **kwargs: object) -> SimpleNamespace:
            self.attempts += 1
            if self.attempts == 1:
                raise genai_errors.ServerError(
                    503, {"error": {"code": 503, "message": "high demand"}}, None
                )
            return SimpleNamespace(text=fake_payload)

    flaky_client = SimpleNamespace(models=_FlakyModels())
    classifier = GeminiClassifier(
        api_key="test-key",
        model="gemini-3.6-flash",
        client=flaky_client,
        max_retries=2,
        retry_delay=0.0,
    )

    result = classifier.classify(SAMPLE_EMAILS[0])
    assert result.category is Category.URGENT_SUPPORT
    assert flaky_client.models.attempts == 2


def test_mock_classifier_covers_all_four_categories() -> None:
    classifier = MockClassifier()
    results = [classifier.classify(email) for email in SAMPLE_EMAILS]

    assert [r.category for r in results] == [
        Category.URGENT_SUPPORT,
        Category.SALES_LEAD,
        Category.BILLING_INVOICE,
        Category.LOW_PRIORITY_NEWSLETTER,
    ]
    assert all(1 <= r.priority <= 5 for r in results)
    assert results[0].suggested_reply != ""
    assert results[1].suggested_reply != ""
    assert results[2].suggested_reply == ""
    assert results[3].suggested_reply == ""
