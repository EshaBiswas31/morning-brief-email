"""Deliver the brief: email (default), Telegram (optional), GitHub run page, and a saved copy."""
from __future__ import annotations

import html
import logging
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

import requests

log = logging.getLogger(__name__)


# ── Email ─────────────────────────────────────────────────────

def build_email(text: str, subject: str, sender: str, recipients: list[str]) -> EmailMessage:
    """Plain-text email with an HTML version that keeps the line breaks."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(text)
    body = html.escape(text).replace("\n", "<br>\n")
    msg.add_alternative(
        '<div style="font-family:Segoe UI,Arial,sans-serif;font-size:15px;'
        f'line-height:1.5;max-width:640px">{body}</div>',
        subtype="html",
    )
    return msg


def send_email(text: str, subject: str) -> None:
    """Send through Gmail using an app password (see README)."""
    sender = os.environ.get("EMAIL_ADDRESS", "").strip()
    password = os.environ.get("EMAIL_APP_PASSWORD", "").replace(" ", "")
    to = os.environ.get("EMAIL_TO", "").strip() or sender
    if not sender or not password:
        raise RuntimeError("EMAIL_ADDRESS and EMAIL_APP_PASSWORD must be set")

    recipients = [r.strip() for r in to.split(",") if r.strip()]
    msg = build_email(text, subject, sender, recipients)
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    with smtplib.SMTP_SSL(host, 465, timeout=30) as server:
        server.login(sender, password)
        server.send_message(msg)
    log.info("Emailed to %s", ", ".join(recipients))


# ── Telegram (optional) ───────────────────────────────────────

TELEGRAM_LIMIT = 4000  # Telegram's hard cap is 4096 characters per message


def split_message(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Split on line breaks so no chunk exceeds the Telegram limit."""
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:  # a single monster line
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit:
            chunks.append(current)
            current = ""
        current += line
    if current.strip():
        chunks.append(current)
    return [c.rstrip("\n") for c in chunks]


def send_telegram(text: str) -> None:
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_TOKEN and TELEGRAM_CHAT_ID must be set")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for chunk in split_message(text):
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True},
            timeout=20,
        )
        if not resp.ok:
            raise RuntimeError(f"Telegram error {resp.status_code}: {resp.text}")
    log.info("Sent to Telegram (%d message(s))", len(split_message(text)))


# ── GitHub run page + local copy ──────────────────────────────

def github_summary(text: str) -> bool:
    """Show the brief on the GitHub Actions run page. Returns False outside Actions."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return False
    with open(path, "a", encoding="utf-8") as f:
        f.write("```text\n" + text.replace("```", "'''") + "\n```\n")
    return True


def save(text: str, folder: str, day: str) -> Path:
    path = Path(folder) / f"{day}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
