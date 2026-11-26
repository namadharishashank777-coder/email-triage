"""Gmail API client for reading unread threads, applying labels, and saving drafts."""

import base64
import html
import re
from email.message import EmailMessage as MimeEmailMessage
from pathlib import Path
from typing import Any, Protocol

from email_triage.models import EmailMessage, ThreadMessage

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
]

_TAG_STRIP_RE = re.compile(r"<[^>]+>")
_STYLE_SCRIPT_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\n{3,}")


class EmailClient(Protocol):
    """Protocol for email backends (live Gmail or mock client)."""

    def list_unread_emails(self, max_results: int = 10) -> list[EmailMessage]:
        """Fetch unread emails along with prior thread context."""
        ...

    def apply_label(self, message_id: str, label_name: str) -> str:
        """Apply a label to a message and return the label identifier."""
        ...

    def create_draft(self, email: EmailMessage, reply_body: str) -> str:
        """Save a draft reply in the email thread without sending; return draft ID."""
        ...


def _decode_base64url(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="replace")


def _strip_html(raw_html: str) -> str:
    no_scripts = _STYLE_SCRIPT_RE.sub("", raw_html)
    text = _TAG_STRIP_RE.sub(" ", no_scripts)
    text = html.unescape(text)
    lines = [line.strip() for line in text.splitlines()]
    collapsed = "\n".join(line for line in lines if line)
    return _WHITESPACE_RE.sub("\n\n", collapsed).strip()


def extract_body_from_payload(payload: dict[str, Any]) -> str:
    """Recursively extract plain-text body (or stripped HTML fallback) from Gmail payload."""
    if not payload:
        return ""

    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data")

    if mime_type == "text/plain" and body_data:
        return _decode_base64url(body_data).strip()

    parts = payload.get("parts") or []
    html_candidates: list[str] = []
    for part in parts:
        part_mime = part.get("mimeType", "")
        if part_mime == "text/plain":
            text = extract_body_from_payload(part)
            if text:
                return text
        elif part_mime.startswith("multipart/"):
            nested = extract_body_from_payload(part)
            if nested:
                return nested
        elif part_mime == "text/html":
            part_data = part.get("body", {}).get("data")
            if part_data:
                html_candidates.append(_strip_html(_decode_base64url(part_data)))

    if html_candidates:
        return "\n".join(candidate for candidate in html_candidates if candidate).strip()

    if mime_type == "text/html" and body_data:
        return _strip_html(_decode_base64url(body_data))

    if body_data:
        return _decode_base64url(body_data).strip()

    return ""


def _get_header(headers: list[dict[str, str]], name: str) -> str:
    target = name.casefold()
    for header in headers:
        if header.get("name", "").casefold() == target:
            return header.get("value", "")
    return ""


def _reply_subject(subject: str) -> str:
    stripped = subject.strip()
    if stripped.casefold().startswith("re:"):
        return stripped
    return f"Re: {stripped}" if stripped else "Re:"


class GmailClient:
    """Gmail API wrapper that reads unread threads, applies labels, and saves drafts only."""

    def __init__(
        self,
        credentials_path: Path = Path("credentials.json"),
        token_path: Path = Path("token.json"),
        service: Any = None,
    ) -> None:
        self.credentials_path = credentials_path
        self.token_path = token_path
        self._service = service
        self._label_cache: dict[str, str] = {}

    def _get_service(self) -> Any:
        if self._service is not None:
            return self._service

        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds: Credentials | None = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), GMAIL_SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(
                        f"Gmail OAuth credentials not found at {self.credentials_path}. "
                        "Download desktop OAuth credentials from Google Cloud Console."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), GMAIL_SCOPES
                )
                creds = flow.run_local_server(port=0)

            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(creds.to_json(), encoding="utf-8")

        self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def _fetch_thread_context(self, thread_id: str, current_message_id: str) -> list[ThreadMessage]:
        service = self._get_service()
        thread = (
            service.users()
            .threads()
            .get(userId="me", id=thread_id, format="full")
            .execute()
        )
        prior_messages: list[ThreadMessage] = []
        for msg in thread.get("messages", []):
            if msg.get("id") == current_message_id:
                break
            payload = msg.get("payload", {})
            headers = payload.get("headers", [])
            prior_messages.append(
                ThreadMessage(
                    sender=_get_header(headers, "From"),
                    subject=_get_header(headers, "Subject"),
                    body=extract_body_from_payload(payload) or msg.get("snippet", ""),
                    received_at=_get_header(headers, "Date"),
                )
            )
        return prior_messages

    def list_unread_emails(self, max_results: int = 10) -> list[EmailMessage]:
        """List unread Gmail messages with full body and prior thread context."""
        service = self._get_service()
        response = (
            service.users()
            .messages()
            .list(userId="me", q="is:unread", maxResults=max_results)
            .execute()
        )
        summaries = response.get("messages", [])
        emails: list[EmailMessage] = []

        for summary in summaries:
            msg_id = summary["id"]
            full_msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )
            payload = full_msg.get("payload", {})
            headers = payload.get("headers", [])
            thread_id = full_msg.get("threadId", msg_id)
            body = extract_body_from_payload(payload) or full_msg.get("snippet", "")
            thread_context = self._fetch_thread_context(thread_id, msg_id)

            emails.append(
                EmailMessage(
                    id=msg_id,
                    thread_id=thread_id,
                    sender=_get_header(headers, "From"),
                    subject=_get_header(headers, "Subject") or "(No Subject)",
                    body=body,
                    thread_context=thread_context,
                    received_at=_get_header(headers, "Date"),
                    message_id_header=_get_header(headers, "Message-ID"),
                    references_header=_get_header(headers, "References"),
                )
            )

        return emails

    def _get_or_create_label_id(self, label_name: str) -> str:
        if label_name in self._label_cache:
            return self._label_cache[label_name]

        service = self._get_service()
        if not self._label_cache:
            existing = service.users().labels().list(userId="me").execute()
            for label in existing.get("labels", []):
                self._label_cache[label["name"]] = label["id"]

        if label_name in self._label_cache:
            return self._label_cache[label_name]

        created = (
            service.users()
            .labels()
            .create(
                userId="me",
                body={
                    "name": label_name,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                },
            )
            .execute()
        )
        label_id = created["id"]
        self._label_cache[label_name] = label_id
        return label_id

    def apply_label(self, message_id: str, label_name: str) -> str:
        """Apply a Gmail label to a message, creating the label if needed."""
        service = self._get_service()
        label_id = self._get_or_create_label_id(label_name)
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": [label_id]},
        ).execute()
        return label_id

    def create_draft(self, email: EmailMessage, reply_body: str) -> str:
        """Create a Gmail Draft reply in the same thread without sending."""
        service = self._get_service()
        mime_msg = MimeEmailMessage()
        mime_msg["To"] = email.sender
        mime_msg["Subject"] = _reply_subject(email.subject)
        if email.message_id_header:
            mime_msg["In-Reply-To"] = email.message_id_header
            refs = " ".join(
                part for part in [email.references_header, email.message_id_header] if part
            )
            mime_msg["References"] = refs
        mime_msg.set_content(reply_body)

        raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("ascii")
        draft = (
            service.users()
            .drafts()
            .create(
                userId="me",
                body={
                    "message": {
                        "raw": raw,
                        "threadId": email.thread_id,
                    }
                },
            )
            .execute()
        )
        return draft["id"]
