"""Command-line interface for running the Email Triage Agent."""

import argparse
import json
import sys

from email_triage.agent import EmailTriageAgent
from email_triage.classifier import (
    AntigravityClassifier,
    EmailClassifier,
    GeminiClassifier,
    MockClassifier,
)
from email_triage.config import TriageConfig
from email_triage.gmail_client import EmailClient, GmailClient
from email_triage.mock_data import MockEmailClient
from email_triage.models import DRAFT_ELIGIBLE_CATEGORIES, TriageActionRecord


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="email-triage",
        description="Triage unread Gmail emails with Gemini / Antigravity SDK.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze emails without modifying Gmail labels or creating real drafts.",
    )
    parser.add_argument(
        "--mock-emails",
        action="store_true",
        help="Use built-in sample emails instead of connecting to live Gmail.",
    )
    parser.add_argument(
        "--mock-llm",
        action="store_true",
        help="Use the offline deterministic classifier instead of calling an LLM API.",
    )
    parser.add_argument(
        "--backend",
        choices=["gemini", "antigravity", "mock"],
        default=None,
        help="Classifier backend override (defaults to TRIAGE_BACKEND from .env).",
    )
    parser.add_argument(
        "--max-emails",
        type=int,
        default=None,
        help="Maximum number of unread emails to process.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print triage results as formatted JSON.",
    )
    return parser


def _select_classifier(backend: str, config: TriageConfig) -> EmailClassifier:
    if backend == "mock":
        return MockClassifier()
    if backend == "antigravity":
        return AntigravityClassifier()
    if backend == "gemini":
        return GeminiClassifier(api_key=config.gemini_api_key, model=config.gemini_model)
    raise ValueError(f"Unsupported backend: {backend!r}")


def _format_human_summary(records: list[TriageActionRecord]) -> str:
    if not records:
        return "No unread emails found."

    lines: list[str] = []
    for record in records:
        would_draft = (
            record.triage.category in DRAFT_ELIGIBLE_CATEGORIES
            and bool(record.triage.suggested_reply.strip())
        )
        draft_status = (
            f"YES ({record.draft_id})"
            if record.draft_created
            else ("WOULD DRAFT (dry-run)" if record.dry_run and would_draft else "NO")
        )
        label_status = (
            f"{record.label_applied} (dry-run)" if record.dry_run else record.label_applied
        )
        lines.append(
            f"[{record.email_id}] P{record.triage.priority} | {record.triage.category.value}\n"
            f"  From:   {record.sender}\n"
            f"  Subj:   {record.subject}\n"
            f"  Label:  {label_status}\n"
            f"  Draft:  {draft_status}\n"
            f"  Action: {record.triage.action_required}"
        )
    return "\n\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    args = build_parser().parse_args(argv)
    config = TriageConfig.from_env()

    dry_run = args.dry_run or config.dry_run
    max_emails = args.max_emails if args.max_emails is not None else config.max_emails
    backend = "mock" if args.mock_llm else (args.backend or config.backend)

    email_client: EmailClient = (
        MockEmailClient()
        if args.mock_emails
        else GmailClient(
            credentials_path=config.gmail_credentials_path,
            token_path=config.gmail_token_path,
        )
    )
    classifier = _select_classifier(backend, config)

    agent = EmailTriageAgent(
        email_client=email_client,
        classifier=classifier,
        dry_run=dry_run,
    )
    records = agent.run(max_emails=max_emails)

    if args.json_output:
        print(json.dumps([record.model_dump(mode="json") for record in records], indent=2))
    else:
        print(_format_human_summary(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
