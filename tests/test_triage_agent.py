"""Unit tests for EmailTriageAgent orchestration and Gmail safety guarantees."""

import base64

from email_triage.agent import EmailTriageAgent
from email_triage.classifier import MockClassifier
from email_triage.gmail_client import GmailClient
from email_triage.mock_data import SAMPLE_EMAILS, MockEmailClient
from email_triage.models import CATEGORY_LABELS, Category, EmailMessage, TriageResult


def test_agent_labels_all_and_drafts_only_urgent_and_sales() -> None:
    client = MockEmailClient()
    classifier = MockClassifier()
    agent = EmailTriageAgent(email_client=client, classifier=classifier, dry_run=False)

    records = agent.run(max_emails=10)

    assert len(records) == 4
    assert client.applied_labels == [
        ("msg-001", CATEGORY_LABELS[Category.URGENT_SUPPORT]),
        ("msg-002", CATEGORY_LABELS[Category.SALES_LEAD]),
        ("msg-003", CATEGORY_LABELS[Category.BILLING_INVOICE]),
        ("msg-004", CATEGORY_LABELS[Category.LOW_PRIORITY_NEWSLETTER]),
    ]

    # Drafts must ONLY be created for Urgent Support and Sales Lead.
    assert len(client.created_drafts) == 2
    assert [d["email_id"] for d in client.created_drafts] == ["msg-001", "msg-002"]
    assert [r.draft_created for r in records] == [True, True, False, False]


def test_agent_dry_run_performs_no_mutations() -> None:
    client = MockEmailClient()
    classifier = MockClassifier()
    agent = EmailTriageAgent(email_client=client, classifier=classifier, dry_run=True)

    records = agent.run(max_emails=10)

    assert len(records) == 4
    assert all(record.dry_run for record in records)
    assert all(not record.draft_created for record in records)
    assert client.applied_labels == []
    assert client.created_drafts == []


def test_agent_skips_draft_when_suggested_reply_is_blank() -> None:
    class _BlankReplyClassifier:
        def classify(self, email: EmailMessage) -> TriageResult:
            return TriageResult(
                category=Category.URGENT_SUPPORT,
                priority=5,
                action_required="Call customer directly.",
                suggested_reply="",
            )

    client = MockEmailClient(emails=[SAMPLE_EMAILS[0]])
    agent = EmailTriageAgent(
        email_client=client,
        classifier=_BlankReplyClassifier(),
        dry_run=False,
    )
    records = agent.run(max_emails=1)

    assert len(client.applied_labels) == 1
    assert client.created_drafts == []
    assert records[0].draft_created is False


def test_gmail_client_reads_thread_creates_label_and_draft_without_send() -> None:
    def _b64(text: str) -> str:
        return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")

    class _Exec:
        def __init__(self, payload: object) -> None:
            self._payload = payload

        def execute(self) -> object:
            return self._payload

    class _FakeMessages:
        def __init__(self) -> None:
            self.modified: list[tuple[str, dict[str, object]]] = []
            self.send_called = False

        def list(self, **kwargs: object) -> _Exec:
            return _Exec({"messages": [{"id": "m2", "threadId": "t1"}]})

        def get(self, userId: str, id: str, format: str = "full") -> _Exec:
            return _Exec(
                {
                    "id": "m2",
                    "threadId": "t1",
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": [
                            {"name": "From", "value": "buyer@corp.test"},
                            {"name": "Subject", "value": "Enterprise Quote"},
                            {"name": "Message-ID", "value": "<m2@corp.test>"},
                        ],
                        "body": {"data": _b64("Can you quote 200 seats?")},
                    },
                }
            )

        def modify(self, userId: str, id: str, body: dict[str, object]) -> _Exec:
            self.modified.append((id, body))
            return _Exec({"id": id})

        def send(self, **kwargs: object) -> _Exec:  # pragma: no cover
            self.send_called = True
            raise AssertionError("send() must never be called")

    class _FakeThreads:
        def get(self, userId: str, id: str, format: str = "full") -> _Exec:
            return _Exec(
                {
                    "id": "t1",
                    "messages": [
                        {
                            "id": "m1",
                            "payload": {
                                "mimeType": "text/plain",
                                "headers": [
                                    {"name": "From", "value": "buyer@corp.test"},
                                    {"name": "Subject", "value": "Intro"},
                                ],
                                "body": {"data": _b64("Initial inquiry")},
                            },
                        },
                        {
                            "id": "m2",
                            "payload": {
                                "mimeType": "text/plain",
                                "headers": [
                                    {"name": "From", "value": "buyer@corp.test"},
                                    {"name": "Subject", "value": "Enterprise Quote"},
                                ],
                                "body": {"data": _b64("Can you quote 200 seats?")},
                            },
                        },
                    ],
                }
            )

    class _FakeLabels:
        def __init__(self) -> None:
            self.created: list[dict[str, object]] = []

        def list(self, userId: str) -> _Exec:
            return _Exec({"labels": []})

        def create(self, userId: str, body: dict[str, object]) -> _Exec:
            self.created.append(body)
            return _Exec({"id": "LBL_1", "name": body["name"]})

    class _FakeDrafts:
        def __init__(self) -> None:
            self.created: list[dict[str, object]] = []
            self.send_called = False

        def create(self, userId: str, body: dict[str, object]) -> _Exec:
            self.created.append(body)
            return _Exec({"id": "DR_1"})

        def send(self, **kwargs: object) -> _Exec:  # pragma: no cover
            self.send_called = True
            raise AssertionError("drafts.send() must never be called")

    class _FakeUsers:
        def __init__(self) -> None:
            self._messages = _FakeMessages()
            self._threads = _FakeThreads()
            self._labels = _FakeLabels()
            self._drafts = _FakeDrafts()

        def messages(self) -> _FakeMessages:
            return self._messages

        def threads(self) -> _FakeThreads:
            return self._threads

        def labels(self) -> _FakeLabels:
            return self._labels

        def drafts(self) -> _FakeDrafts:
            return self._drafts

    class _FakeService:
        def __init__(self) -> None:
            self._users = _FakeUsers()

        def users(self) -> _FakeUsers:
            return self._users

    fake_service = _FakeService()
    gmail = GmailClient(service=fake_service)

    unread = gmail.list_unread_emails(max_results=5)
    assert len(unread) == 1
    assert unread[0].body == "Can you quote 200 seats?"
    assert len(unread[0].thread_context) == 1
    assert unread[0].thread_context[0].body == "Initial inquiry"

    gmail.apply_label("m2", "Triage/Sales Lead")
    draft_id = gmail.create_draft(unread[0], "Thanks! Sending a quote shortly.")

    assert draft_id == "DR_1"
    assert fake_service.users().labels().created[0]["name"] == "Triage/Sales Lead"
    assert fake_service.users().messages().modified == [
        ("m2", {"addLabelIds": ["LBL_1"]})
    ]
    assert fake_service.users().drafts().created[0]["message"]["threadId"] == "t1"
    assert fake_service.users().messages().send_called is False
    assert fake_service.users().drafts().send_called is False
