"""
GEO Pulse — a Caspian agent wrapping the GEO Auditor pipeline.

One identity, one handler, two channels (email + Telegram — both free,
no signup, per the Caspian README). Two jobs:

1. On-demand audits: message it a URL ("audit https://acme.com as
   fintech software in Bangalore") and it runs the existing GEO Auditor
   pipeline (main.run_audit) and replies with the score + top fixes in
   the same thread it was asked in.

2. Real-world AI-referral log — the part a synthetic test-query tool
   structurally cannot do. Every inbound message that ISN'T an audit
   request gets one soft, one-line follow-up: did an AI point you here?
   Answers land in caspian_referral_log.jsonl as a ground-truth signal,
   separate from and complementary to visibility/live_test.py's
   simulated queries.

Setup:
  pip install caspian-sdk python-dotenv
  comm init                      # writes COMM_API_KEY / COMM_BASE_URL to .env
  echo "TELEGRAM_BOT_TOKEN=..." >> .env   # from @BotFather
  python caspian_agent.py
"""

import os
import re
import json
import threading
from datetime import datetime

from dotenv import load_dotenv
from caspian_sdk import CommClient, Message
from playwright.sync_api import sync_playwright

from main import run_audit
from report import generator
from pathlib import Path

load_dotenv()

client = CommClient()  # reads COMM_API_KEY / COMM_BASE_URL from .env

REFERRAL_LOG = os.path.join(os.path.dirname(__file__), "caspian_referral_log.jsonl")
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

AI_KEYWORDS = [
    "chatgpt", "gpt", "gemini", "claude", "perplexity", "copilot",
    "ai told", "asked ai", "an ai", "google ai", "bard",
]
URL_RE = re.compile(r"https?://\S+")

# Keyed by conversation_id (Caspian's cross-channel thread identity) rather
# than a per-channel sender id, so "are we mid-conversation with this
# person" works the same regardless of which channel they wrote in on.
_awaiting_referral_answer: dict[str, bool] = {}


def _html_to_pdf(html_path: str, pdf_path: str):
    """Render the report to PDF with real Chromium (via Playwright) --
    same rendering engine as the browser, so flexbox/grid/CSS variables
    in report/generator.py just work, unlike weasyprint (native GTK/pango
    deps, a real pain on Windows) or xhtml2pdf (doesn't support CSS
    variables or flexbox/grid at all -- verified, it visibly breaks this
    template's layout)."""
    print(f"[debug] Converting HTML to PDF...")
    print(f"        HTML Path: {html_path}")
    print(f"        PDF Path:  {pdf_path}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        file_uri = Path(html_path).resolve().as_uri()
        print(f"        Resolved URI: {file_uri}")
        page.goto(file_uri, wait_until="load")
        page.pdf(path=pdf_path, print_background=True, format="A4")
        browser.close()
    print(f"[debug] PDF conversion complete. Exists: {os.path.exists(pdf_path)}, Size: {os.path.getsize(pdf_path)} bytes")


def _looks_like_audit_request(text: str) -> bool:
    return bool(URL_RE.search(text)) and any(
        kw in text.lower() for kw in ("audit", "check", "geo", "score")
    )


def _parse_request(text: str, url: str) -> tuple[str, str]:
    """Best-effort slot-filling from a single free-text message:
    'audit <url> as <category> [in <location>]'.
    Location is stripped off the end first (whatever's after the last
    standalone 'in'), then everything after 'as' in what's left is the
    category -- verbatim, punctuation and hyphens included, rather than
    an alnum-only character class that broke on things like
    'all-in-one'. Hackathon-speed heuristic, not an NLU pass — flagged
    as such in the README."""
    rest = text.replace(url, "").strip()

    location = ""
    loc_match = re.search(r"\bin\s+([\w][\w,.\-' ]*)$", rest, re.IGNORECASE)
    if loc_match:
        location = loc_match.group(1).strip()
        rest = rest[: loc_match.start()].strip()

    category = ""
    cat_match = re.search(r"\bas\s+(.+)$", rest, re.IGNORECASE)
    if cat_match:
        category = cat_match.group(1).strip()

    return category, location


def _run_and_reply(message: Message, url: str, category: str, location: str):
    business_name = url.split("//")[-1].split("/")[0]
    print(f"[caspian_agent] Audit request detected -> {url} (category={category!r}, location={location!r})")
    message.reply(
        f"On it — auditing {business_name} now. This takes about 60-90s, "
        f"I'll follow up right here."
    )
    try:
        results = run_audit(url, business_name, category or "general", location)
        score = results["geo_score"]

        safe = re.sub(r"[^a-z0-9]+", "-", business_name.lower()).strip("-")
        html_path = os.path.join(
            REPORTS_DIR, f"{safe}-{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        )
        generator.generate(results, html_path)

        # Render the same report to PDF so it can go out as a real attachment --
        # Telegram and email both carry files natively (per the media param docs:
        # "channels that carry files send them natively"); channels that can't
        # fall back to a link automatically.
        pdf_path = html_path.replace(".html", ".pdf")
        try:
            _html_to_pdf(html_path, pdf_path)
            pdf_attached = True
        except Exception as pdf_exc:
            print(f"[caspian_agent] PDF render failed, sending text only: {pdf_exc}")
            import traceback
            traceback.print_exc()
            pdf_attached = False

        fixes = (
            results["answer_readiness"].get("fixes", [])
            + results["ai_authority"].get("fixes", [])
        )[:3]

        summary = (
            f"GEO Score: {score['score']}/100 ({score['band']})\n"
            f"{score['description']}\n\n"
            f"Crawlability {results['crawlability']['score']} · "
            f"Entity Authority {results['ai_authority']['score']} · "
            f"Answer Readiness {results['answer_readiness']['score']}"
        )
        if fixes:
            summary += "\n\nTop fixes:\n" + "\n".join(f"- {f['title']}" for f in fixes)

        if pdf_attached and os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
            import base64
            encoded_data = base64.b64encode(pdf_bytes).decode("ascii")
            print(f"[debug] Encoded PDF base64 length: {len(encoded_data)} chars")

            media = [{
                "data": encoded_data,
                "mime_type": "application/pdf",
                "name": f"{safe}-geo-audit.pdf",
            }]
            summary += "\n\nFull report attached as a PDF."
            print("[debug] Calling message.reply with media attachment...")
            message.reply(summary, media=media)
            print("[debug] message.reply completed successfully.")
        else:
            print("[debug] Skipping PDF attachment: pdf_attached is False or file missing.")
            message.reply(summary)
    except Exception as exc:
        message.reply(
            f"Couldn't finish that audit ({exc}). Try a plain https:// URL, "
            f"e.g. 'audit https://acme.com as project management software'."
        )


def _log_referral(conversation_id: str, channel: str, sender: dict | None, text: str, is_ai_referral: bool):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "conversation_id": conversation_id,
        "channel": channel,
        "sender": sender,
        "message": text,
        "ai_referral": is_ai_referral,
    }
    with open(REFERRAL_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


@client.on_message
def handle(message: Message):
    text = (message.text or "").strip()
    if not text:
        return

    # An audit request always wins, even mid-referral-conversation --
    # don't let a stale "are we waiting on an answer?" flag eat a real request.
    if _looks_like_audit_request(text):
        _awaiting_referral_answer.pop(message.conversation_id, None)
        url = URL_RE.search(text).group(0)
        category, location = _parse_request(text, url)
        threading.Thread(
            target=_run_and_reply, args=(message, url, category, location), daemon=True
        ).start()
        return

    if message.conversation_id in _awaiting_referral_answer:
        is_ai = any(kw in text.lower() for kw in AI_KEYWORDS)
        _log_referral(message.conversation_id, message.channel, message.sender, text, is_ai)
        del _awaiting_referral_answer[message.conversation_id]
        message.reply(
            "That's logged as a real AI-referral data point — thank you!"
            if is_ai else "Got it, thanks for the context!"
        )
        return

    message.reply(
        "Hi! Send me a business URL to audit its AI visibility "
        "(e.g. 'audit https://acme.com as project management software'). "
        "Quick one first though — did an AI like ChatGPT or Gemini point you "
        "here today, or how'd you find this?"
    )
    _awaiting_referral_answer[message.conversation_id] = True


if __name__ == "__main__":
    print("GEO Pulse — connecting channels...")

    inbox = client.connect_email(display_name="GEO Pulse")
    print("  email:", inbox["address"])

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if telegram_token:
        client.connect_telegram(bot_token=telegram_token)
        print("  telegram: connected")
    else:
        print("  telegram: skipped (no TELEGRAM_BOT_TOKEN in .env)")

    print("\nOne handler, live on every connected channel. Ctrl+C to stop.\n")
    client.listen(ack="On it…")