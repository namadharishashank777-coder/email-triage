"""Core email triage orchestration logic."""

from email_triage.classifier import EmailClassifier
from email_triage.gmail_client import EmailClient
from email_triage.models import (
    CATEGORY_LABELS,
    DRAFT_ELIGIBLE_CATEGORIES,
    Category,
    TriageActionRecord,
)


class EmailTriageAgent:
    """Fetches unread emails, classifies them, applies labels, and drafts eligible replies."""

    def __init__(
        self,
        email_client: EmailClient,
        classifier: EmailClassifier,
        dry_run: bool = False,
        label_map: dict[Category, str] | None = None,
    ) -> None:
        self.email_client = email_client
        self.classifier = classifier
        self.dry_run = dry_run
        self.label_map = label_map or CATEGORY_LABELS

    def run(self, max_emails: int = 10) -> list[TriageActionRecord]:
        """Triage up to `max_emails` unread messages without ever auto-sending replies."""
        unread_emails = self.email_client.list_unread_emails(max_results=max_emails)
        records: list[TriageActionRecord] = []

        for email in unread_emails:
            triage = self.classifier.classify(email)
            label_name = self.label_map[triage.category]
            should_draft = (
                triage.category in DRAFT_ELIGIBLE_CATEGORIES
                and bool(triage.suggested_reply.strip())
            )

            draft_id: str | None = None
            draft_created = False

            if not self.dry_run:
                self.email_client.apply_label(email.id, label_name)
                if should_draft:
                    draft_id = self.email_client.create_draft(email, triage.suggested_reply)
                    draft_created = True

            records.append(
                TriageActionRecord(
                    email_id=email.id,
                    thread_id=email.thread_id,
                    sender=email.sender,
                    subject=email.subject,
                    triage=triage,
                    label_applied=label_name,
                    draft_created=draft_created,
                    draft_id=draft_id,
                    dry_run=self.dry_run,
                )
            )

        return records
