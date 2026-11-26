"""Sample unread emails and in-memory mock Gmail client for local dry-run testing."""

from email_triage.models import EmailMessage, ThreadMessage

SAMPLE_EMAILS: list[EmailMessage] = [
    EmailMessage(
        id="msg-001",
        thread_id="thr-001",
        sender="Maya Lin <maya.lin@acmehealth.io>",
        subject="URGENT: Production API returning 500 errors after webhook update",
        received_at="Thu, 26 Nov 2026 00:05:00 +0530",
        message_id_header="<msg-001@acmehealth.io>",
        thread_context=[
            ThreadMessage(
                sender="Maya Lin <maya.lin@acmehealth.io>",
                subject="Webhook migration check",
                body="We are migrating our webhook secret tonight at 23:30 IST.",
                received_at="Wed, 25 Nov 2026 23:15:00 +0530",
            )
        ],
        body=(
            "Our production checkout service has been down for 15 minutes with HTTP 500 "
            "responses on every webhook event. Customers cannot complete orders. "
            "Please escalate immediately!"
        ),
    ),
    EmailMessage(
        id="msg-002",
        thread_id="thr-002",
        sender="Daniel Park <dpark@northstarlabs.com>",
        subject="Enterprise pricing and demo request for 120 seats",
        received_at="Thu, 26 Nov 2026 00:10:00 +0530",
        message_id_header="<msg-002@northstarlabs.com>",
        thread_context=[
            ThreadMessage(
                sender="Daniel Park <dpark@northstarlabs.com>",
                subject="Quick question on SSO",
                body="Does your platform support Okta SAML on annual plans?",
                received_at="Wed, 25 Nov 2026 19:40:00 +0530",
            )
        ],
        body=(
            "Thanks for confirming SSO! We would like an annual enterprise quote for "
            "120 seats and a live demo for our security team early next week."
        ),
    ),
    EmailMessage(
        id="msg-003",
        thread_id="thr-003",
        sender="CloudHost Billing <billing@cloudhost.example>",
        subject="Invoice #INV-2026-1142 for November Usage",
        received_at="Wed, 25 Nov 2026 21:00:00 +0530",
        message_id_header="<msg-003@cloudhost.example>",
        body=(
            "Your monthly invoice #INV-2026-1142 for $428.50 has been generated and "
            "paid via auto-pay ending in 4242. Download your PDF receipt from the billing portal."
        ),
    ),
    EmailMessage(
        id="msg-004",
        thread_id="thr-004",
        sender="DevPulse Weekly <digest@devpulse.example>",
        subject="Issue #218: Python 3.13 tips, AI agents, and Postgres indexing",
        received_at="Wed, 25 Nov 2026 18:30:00 +0530",
        message_id_header="<msg-004@devpulse.example>",
        body=(
            "Welcome to this week's DevPulse newsletter! Read our top 5 articles on "
            "async Python patterns, structured outputs, and query tuning. Unsubscribe anytime."
        ),
    ),
]


class MockEmailClient:
    """In-memory EmailClient storing applied labels and drafted replies."""

    def __init__(self, emails: list[EmailMessage] | None = None) -> None:
        self.emails = list(emails if emails is not None else SAMPLE_EMAILS)
        self.applied_labels: list[tuple[str, str]] = []
        self.created_drafts: list[dict[str, str]] = []

    def list_unread_emails(self, max_results: int = 10) -> list[EmailMessage]:
        """Return up to `max_results` sample unread emails."""
        return self.emails[:max_results]

    def apply_label(self, message_id: str, label_name: str) -> str:
        """Record label application in memory."""
        self.applied_labels.append((message_id, label_name))
        return f"mock-label:{label_name}"

    def create_draft(self, email: EmailMessage, reply_body: str) -> str:
        """Record draft creation in memory without ever sending."""
        draft_id = f"mock-draft-{len(self.created_drafts) + 1}"
        self.created_drafts.append(
            {
                "draft_id": draft_id,
                "email_id": email.id,
                "thread_id": email.thread_id,
                "to": email.sender,
                "subject": email.subject,
                "body": reply_body,
            }
        )
        return draft_id
