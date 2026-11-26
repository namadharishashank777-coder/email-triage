"""Unit tests for triage JSON parsing and schema validation."""

import json
import pytest

from email_triage.models import Category
from email_triage.parser import TriageParseError, parse_triage_json


@pytest.mark.parametrize(
    ("category_str", "expected_category", "priority"),
    [
        ("Urgent Support", Category.URGENT_SUPPORT, 5),
        ("Sales Lead", Category.SALES_LEAD, 4),
        ("Billing/Invoice", Category.BILLING_INVOICE, 2),
        ("Low Priority/Newsletter", Category.LOW_PRIORITY_NEWSLETTER, 1),
    ],
)
def test_parse_valid_json_all_categories(
    category_str: str, expected_category: Category, priority: int
) -> None:
    payload = json.dumps(
        {
            "category": category_str,
            "priority": priority,
            "action_required": "Review and route appropriately.",
            "suggested_reply": "Hello, thank you for reaching out.",
        }
    )
    result = parse_triage_json(payload)
    assert result.category is expected_category
    assert result.priority == priority
    assert result.action_required == "Review and route appropriately."
    assert result.suggested_reply == "Hello, thank you for reaching out."


def test_parse_strips_markdown_json_fence() -> None:
    raw = """```json
    {
      "category": "Sales Lead",
      "priority": 4,
      "action_required": "Schedule a product demo.",
      "suggested_reply": "Happy to set up a demo this week."
    }
    ```"""
    result = parse_triage_json(raw)
    assert result.category is Category.SALES_LEAD
    assert result.priority == 4


def test_parse_extracts_json_wrapped_in_prose() -> None:
    raw = (
        "Here is the classification result:\n"
        '{"category": "Urgent Support", "priority": 5, '
        '"action_required": "Page on-call engineer {immediately}.", '
        '"suggested_reply": "Investigating now."}\n'
        "Let me know if you need anything else."
    )
    result = parse_triage_json(raw)
    assert result.category is Category.URGENT_SUPPORT
    assert result.action_required == "Page on-call engineer {immediately}."


def test_parse_normalizes_category_case_and_whitespace() -> None:
    raw = json.dumps(
        {
            "category": "  urgent   support ",
            "priority": 5,
            "action_required": "Escalate ticket",
            "suggested_reply": None,
        }
    )
    result = parse_triage_json(raw)
    assert result.category is Category.URGENT_SUPPORT
    assert result.suggested_reply == ""


@pytest.mark.parametrize(
    "bad_input",
    [
        "",
        "   ",
        "No JSON here at all",
        '{"category": "Urgent Support", "priority": 5',
        "[1, 2, 3]",
        "{not valid json}",
    ],
)
def test_parse_rejects_malformed_json(bad_input: str) -> None:
    with pytest.raises(TriageParseError):
        parse_triage_json(bad_input)


def test_parse_rejects_unknown_category() -> None:
    raw = json.dumps(
        {
            "category": "Spam",
            "priority": 1,
            "action_required": "Ignore",
            "suggested_reply": "",
        }
    )
    with pytest.raises(TriageParseError):
        parse_triage_json(raw)


@pytest.mark.parametrize("bad_priority", [0, 6, -2, True, False, 3.5, "high"])
def test_parse_rejects_invalid_priority(bad_priority: object) -> None:
    raw = json.dumps(
        {
            "category": "Sales Lead",
            "priority": bad_priority,
            "action_required": "Follow up",
            "suggested_reply": "Hi!",
        }
    )
    with pytest.raises(TriageParseError):
        parse_triage_json(raw)


def test_parse_rejects_blank_action_required() -> None:
    raw = json.dumps(
        {
            "category": "Billing/Invoice",
            "priority": 2,
            "action_required": "   ",
            "suggested_reply": "",
        }
    )
    with pytest.raises(TriageParseError):
        parse_triage_json(raw)
