# Email Triage Agent

An AI-powered Gmail triage agent in Python using the Gemini API (`google-genai`) or Google Antigravity SDK (`google-antigravity`) alongside the Gmail API.

## Features
- Fetches unread emails including sender, subject, body, and prior thread context.
- Classifies each email into one of four categories:
  - `Urgent Support`
  - `Sales Lead`
  - `Billing/Invoice`
  - `Low Priority/Newsletter`
- Assigns a priority score (`1`–`5`) and extracts structured JSON (`category`, `priority`, `action_required`, `suggested_reply`).
- Applies corresponding Gmail labels (`Triage/...`) and saves Gmail **Drafts** only for `Urgent Support` and `Sales Lead` emails — **never auto-sends**.
- Includes offline `--dry-run` / `--mock-emails` / `--mock-llm` modes with realistic sample emails and thread context.

## Setup

1. Create and activate a virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -e ".[dev]"
   ```
   *(Optional)* To use the Google Antigravity SDK backend:
   ```powershell
   pip install -e ".[antigravity,dev]"
   ```

2. Configure environment variables:
   ```powershell
   Copy-Item .env.example .env
   ```
   Edit `.env` with your `GEMINI_API_KEY` and Gmail OAuth desktop `credentials.json` path (downloaded from Google Cloud Console with Gmail API enabled).

## Usage

Run completely offline with sample emails and mock classifier:
```powershell
python -m email_triage.cli --dry-run --mock-emails --mock-llm
```

Run against sample emails using your Gemini API key (no Gmail credentials required):
```powershell
python -m email_triage.cli --dry-run --mock-emails
```

Run live against Gmail in dry-run mode (reads unread emails, does not apply labels or create drafts):
```powershell
python -m email_triage.cli --dry-run
```

Run live triage (applies Gmail labels and creates Gmail Drafts for Urgent Support and Sales Leads):
```powershell
python -m email_triage.cli --max-emails 10
```

Output structured JSON:
```powershell
python -m email_triage.cli --dry-run --mock-emails --mock-llm --json
```

## Running Tests

```powershell
pytest
```
