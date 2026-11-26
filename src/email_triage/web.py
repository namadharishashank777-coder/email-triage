"""Web dashboard for Email Triage Agent."""

import json
import os
from pathlib import Path
from flask import Flask, jsonify, render_template_string, request

from email_triage.agent import EmailTriageAgent
from email_triage.classifier import GeminiClassifier, MockClassifier
from email_triage.config import TriageConfig
from email_triage.gmail_client import GmailClient
from email_triage.mock_data import SAMPLE_EMAILS, MockEmailClient

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Email Triage Agent</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0f172a;
            --surface: #1e293b;
            --surface-hover: #334155;
            --border: #334155;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #3b82f6;
            --primary-hover: #2563eb;
            --urgent: #ef4444;
            --sales: #10b981;
            --billing: #f59e0b;
            --low: #64748b;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Inter', -apple-system, sans-serif;
        }

        body {
            background-color: var(--bg);
            color: var(--text);
            padding: 2rem;
            min-height: 100vh;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--border);
        }

        .title-area h1 {
            font-size: 1.8rem;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .badge-live {
            background: #10b98120;
            color: #10b981;
            border: 1px solid #10b98150;
            font-size: 0.75rem;
            padding: 0.2rem 0.5rem;
            border-radius: 9999px;
            font-weight: 600;
        }

        .controls {
            display: flex;
            gap: 1rem;
            align-items: center;
            background: var(--surface);
            padding: 1rem;
            border-radius: 10px;
            border: 1px solid var(--border);
            margin-bottom: 2rem;
            flex-wrap: wrap;
        }

        .control-group {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.9rem;
        }

        select, button {
            padding: 0.6rem 1rem;
            border-radius: 6px;
            font-size: 0.9rem;
            border: 1px solid var(--border);
            background: var(--bg);
            color: var(--text);
            outline: none;
            cursor: pointer;
        }

        button.btn-primary {
            background: var(--primary);
            border-color: var(--primary);
            color: white;
            font-weight: 600;
            transition: background 0.2s;
        }

        button.btn-primary:hover {
            background: var(--primary-hover);
        }

        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
            gap: 1.5rem;
        }

        .email-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 1.25rem;
            display: flex;
            flex-direction: column;
            gap: 1rem;
            transition: transform 0.2s, box-shadow 0.2s;
        }

        .email-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(0,0,0,0.3);
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 0.5rem;
        }

        .category-pill {
            font-size: 0.75rem;
            font-weight: 600;
            padding: 0.25rem 0.6rem;
            border-radius: 6px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .category-urgent { background: rgba(239, 68, 68, 0.2); color: var(--urgent); border: 1px solid rgba(239, 68, 68, 0.3); }
        .category-sales { background: rgba(16, 185, 129, 0.2); color: var(--sales); border: 1px solid rgba(16, 185, 129, 0.3); }
        .category-billing { background: rgba(245, 158, 11, 0.2); color: var(--billing); border: 1px solid rgba(245, 158, 11, 0.3); }
        .category-low { background: rgba(100, 116, 139, 0.2); color: var(--low); border: 1px solid rgba(100, 116, 139, 0.3); }

        .priority-badge {
            font-size: 0.8rem;
            font-weight: 700;
            color: var(--text-muted);
        }

        .email-subject {
            font-size: 1rem;
            font-weight: 600;
            color: var(--text);
            line-height: 1.4;
        }

        .email-sender {
            font-size: 0.82rem;
            color: var(--text-muted);
        }

        .section-label {
            font-size: 0.75rem;
            text-transform: uppercase;
            font-weight: 700;
            color: var(--text-muted);
            margin-bottom: 0.25rem;
        }

        .action-box {
            background: rgba(0, 0, 0, 0.25);
            padding: 0.75rem;
            border-radius: 6px;
            font-size: 0.85rem;
            border-left: 3px solid var(--primary);
        }

        .reply-box {
            background: rgba(16, 185, 129, 0.08);
            border: 1px solid rgba(16, 185, 129, 0.2);
            padding: 0.75rem;
            border-radius: 6px;
            font-size: 0.85rem;
            white-space: pre-wrap;
            color: #d1fae5;
        }

        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.3rem;
            font-size: 0.75rem;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            background: #334155;
            color: #cbd5e1;
            margin-top: auto;
        }

        .loader {
            text-align: center;
            padding: 3rem;
            font-size: 1.1rem;
            color: var(--text-muted);
            display: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="title-area">
                <h1>📬 Email Triage Agent <span class="badge-live">Active</span></h1>
                <p style="color: var(--text-muted); font-size: 0.9rem; margin-top: 0.25rem;">
                    Powered by Gemini AI & Gmail API. Auto-classifies, tags labels, and pre-drafts replies.
                </p>
            </div>
        </header>

        <div class="controls">
            <div class="control-group">
                <label>Backend:</label>
                <select id="backend">
                    <option value="gemini" selected>Google Gemini API (gemini-3.6-flash)</option>
                    <option value="mock">Offline Mock Classifier</option>
                </select>
            </div>

            <div class="control-group">
                <label>Source:</label>
                <select id="source">
                    <option value="mock" selected>Sample Inbox (4 Realistic Threads)</option>
                    <option value="live">Live Gmail Inbox</option>
                </select>
            </div>

            <div class="control-group">
                <label>Mode:</label>
                <select id="dryRun">
                    <option value="true" selected>Dry Run (Preview, No Draft Creation)</option>
                    <option value="false">Live Execution (Apply Labels & Drafts)</option>
                </select>
            </div>

            <button class="btn-primary" id="runBtn" onclick="runTriage()">⚡ Run Triage Now</button>
        </div>

        <div id="loader" class="loader">
            ⏳ Analyzing unread emails with Gemini AI... Please wait.
        </div>

        <div id="results" class="grid"></div>
    </div>

    <script>
        async function runTriage() {
            const btn = document.getElementById('runBtn');
            const loader = document.getElementById('loader');
            const results = document.getElementById('results');

            btn.disabled = true;
            loader.style.display = 'block';
            results.innerHTML = '';

            const backend = document.getElementById('backend').value;
            const source = document.getElementById('source').value;
            const dryRun = document.getElementById('dryRun').value === 'true';

            try {
                const res = await fetch('/api/triage', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ backend, source, dry_run: dryRun })
                });
                const data = await res.json();

                if (!res.ok) {
                    alert('Error: ' + (data.error || 'Failed to triage emails'));
                    return;
                }

                renderEmails(data.records);
            } catch (err) {
                alert('Network or server error: ' + err.message);
            } finally {
                btn.disabled = false;
                loader.style.display = 'none';
            }
        }

        function getCategoryClass(cat) {
            if (cat === 'Urgent Support') return 'category-urgent';
            if (cat === 'Sales Lead') return 'category-sales';
            if (cat === 'Billing/Invoice') return 'category-billing';
            return 'category-low';
        }

        function renderEmails(records) {
            const container = document.getElementById('results');
            if (!records || records.length === 0) {
                container.innerHTML = '<p style="color: var(--text-muted); grid-column: 1/-1;">No unread emails found.</p>';
                return;
            }

            container.innerHTML = records.map(r => {
                const catClass = getCategoryClass(r.triage.category);
                const hasDraft = r.triage.suggested_reply && r.triage.suggested_reply.trim().length > 0;
                
                return `
                <div class="email-card">
                    <div class="card-header">
                        <span class="category-pill ${catClass}">${r.triage.category}</span>
                        <span class="priority-badge">Priority ${r.triage.priority}/5</span>
                    </div>

                    <div>
                        <div class="email-subject">${r.subject}</div>
                        <div class="email-sender">From: ${r.sender}</div>
                    </div>

                    <div>
                        <div class="section-label">Action Required</div>
                        <div class="action-box">${r.triage.action_required}</div>
                    </div>

                    ${hasDraft ? `
                    <div>
                        <div class="section-label">Suggested Draft Reply</div>
                        <div class="reply-box">${r.triage.suggested_reply}</div>
                    </div>
                    ` : ''}

                    <div class="status-badge">
                        🏷️ Label: <b>${r.label_applied}</b>
                        ${r.draft_created ? ' • 📝 Draft Saved' : (r.dry_run && hasDraft ? ' • 📝 Draft Ready (Dry Run)' : '')}
                    </div>
                </div>
                `;
            }).join('');
        }

        // Run automatically on load
        window.onload = runTriage;
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/triage", methods=["POST"])
def triage_endpoint():
    data = request.get_json() or {}
    backend = data.get("backend", "gemini")
    source = data.get("source", "mock")
    dry_run = bool(data.get("dry_run", True))

    config = TriageConfig.from_env()

    if backend == "mock":
        classifier = MockClassifier()
    elif backend == "gemini":
        if not config.gemini_api_key:
            return jsonify({"error": "GEMINI_API_KEY is not set in .env"}), 400
        classifier = GeminiClassifier(
            api_key=config.gemini_api_key,
            model=config.gemini_model,
        )
    else:
        return jsonify({"error": f"Unknown backend: {backend}"}), 400

    if source == "mock":
        email_client = MockEmailClient()
    else:
        if not config.gmail_credentials_path.exists():
            return jsonify({
                "error": f"Gmail credentials file not found at {config.gmail_credentials_path}."
            }), 400
        email_client = GmailClient(
            credentials_path=config.gmail_credentials_path,
            token_path=config.gmail_token_path,
        )

    agent = EmailTriageAgent(
        email_client=email_client,
        classifier=classifier,
        dry_run=dry_run,
    )

    try:
        records = agent.run(max_emails=10)
        return jsonify({
            "status": "success",
            "records": [r.model_dump(mode="json") for r in records],
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def run_server(port: int = 5000):
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    run_server()
