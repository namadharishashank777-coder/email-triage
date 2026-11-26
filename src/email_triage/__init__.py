"""Email Triage Agent package."""

from email_triage.agent import EmailTriageAgent
from email_triage.models import (
    CATEGORY_LABELS,
    DRAFT_ELIGIBLE_CATEGORIES,
    Category,
    EmailMessage,
    ThreadMessage,
    TriageActionRecord,
    TriageResult,
)

__all__ = [
    "CATEGORY_LABELS",
    "DRAFT_ELIGIBLE_CATEGORIES",
    "Category",
    "EmailMessage",
    "EmailTriageAgent",
    "ThreadMessage",
    "TriageActionRecord",
    "TriageResult",
]
