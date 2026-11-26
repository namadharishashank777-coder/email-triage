"""Environment-backed runtime configuration."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class TriageConfig:
    """Configuration loaded from environment variables and .env."""

    backend: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    gmail_credentials_path: Path = Path("credentials.json")
    gmail_token_path: Path = Path("token.json")
    max_emails: int = 10
    dry_run: bool = False

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "TriageConfig":
        """Load configuration from .env (if present) and process environment."""
        load_dotenv(dotenv_path=env_file, override=False)

        raw_max = os.getenv("TRIAGE_MAX_EMAILS", "10").strip()
        try:
            max_emails = max(1, int(raw_max))
        except ValueError as exc:
            raise ValueError(f"Invalid TRIAGE_MAX_EMAILS value: {raw_max!r}") from exc

        backend = os.getenv("TRIAGE_BACKEND", "gemini").strip().lower() or "gemini"
        return cls(
            backend=backend,
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip()
            or "gemini-3.6-flash",
            gmail_credentials_path=Path(
                os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json").strip()
                or "credentials.json"
            ),
            gmail_token_path=Path(
                os.getenv("GMAIL_TOKEN_PATH", "token.json").strip() or "token.json"
            ),
            max_emails=max_emails,
            dry_run=_parse_bool(os.getenv("TRIAGE_DRY_RUN"), default=False),
        )
