"""Data models and policy constants for email triage."""

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class Category(StrEnum):
    """Supported email triage categories."""

    URGENT_SUPPORT = "Urgent Support"
    SALES_LEAD = "Sales Lead"
    BILLING_INVOICE = "Billing/Invoice"
    LOW_PRIORITY_NEWSLETTER = "Low Priority/Newsletter"


CATEGORY_LABELS: dict[Category, str] = {
    Category.URGENT_SUPPORT: "Triage/Urgent Support",
    Category.SALES_LEAD: "Triage/Sales Lead",
    Category.BILLING_INVOICE: "Triage/Billing-Invoice",
    Category.LOW_PRIORITY_NEWSLETTER: "Triage/Low Priority-Newsletter",
}

DRAFT_ELIGIBLE_CATEGORIES: frozenset[Category] = frozenset(
    {Category.URGENT_SUPPORT, Category.SALES_LEAD}
)

_CATEGORY_ALIASES: dict[str, Category] = {
    category.value.casefold(): category for category in Category
}


class ThreadMessage(BaseModel):
    """A preceding message in an email thread for context."""

    sender: str
    subject: str
    body: str
    received_at: str = ""


class EmailMessage(BaseModel):
    """Normalized unread email payload with optional thread history."""

    id: str
    thread_id: str
    sender: str
    subject: str
    body: str
    thread_context: list[ThreadMessage] = Field(default_factory=list)
    received_at: str = ""
    message_id_header: str = ""
    references_header: str = ""


class TriageResult(BaseModel):
    """Structured triage classification and reply suggestion."""

    category: Category
    priority: int = Field(ge=1, le=5)
    action_required: str = Field(min_length=1)
    suggested_reply: str = ""

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, value: object) -> object:
        if isinstance(value, Category):
            return value
        if isinstance(value, str):
            normalized = " ".join(value.strip().split()).casefold()
            if normalized in _CATEGORY_ALIASES:
                return _CATEGORY_ALIASES[normalized]
        return value

    @field_validator("priority", mode="before")
    @classmethod
    def _reject_bool_or_non_int_priority(cls, value: object) -> object:
        # Reject booleans and floats so priority is strictly an integer 1-5.
        if isinstance(value, bool) or isinstance(value, float):
            raise ValueError("priority must be an integer between 1 and 5")
        return value

    @field_validator("action_required", mode="after")
    @classmethod
    def _strip_non_empty_action(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("action_required must not be blank")
        return cleaned

    @field_validator("suggested_reply", mode="before")
    @classmethod
    def _coerce_null_reply(cls, value: object) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError("suggested_reply must be a string")
        return value.strip()


class TriageActionRecord(BaseModel):
    """Outcome record for a single triaged email."""

    email_id: str
    thread_id: str
    sender: str
    subject: str
    triage: TriageResult
    label_applied: str
    draft_created: bool
    draft_id: str | None = None
    dry_run: bool = False
