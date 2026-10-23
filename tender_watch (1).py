"""Tender watcher (email only).

Scans the pages listed in SOURCES, finds links whose text contains one of the
KEYWORDS, and emails you ONE digest with everything new since the last run.
Already-seen items are remembered in seen.json so you never get duplicates.
"""
import json
import os
import re
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# =============================== EDIT THIS ===================================
# name -> URL of a page that LISTS tenders or announcements.
# Replace each URL with the exact page where that institution posts tenders.
SOURCES = {
    "e-Prokurimi": "https://e-prokurimi.rks-gov.net",
    "NLB Banka": "https://www.nlb-kos.com",
    "ProCredit Bank": "https://www.procreditbank-kos.com",
    "AFK": "https://afk-kosovo.com",
}

# A link is reported if its text contains any of these (case-insensitive).
KEYWORDS = [
    "dhurat", "protokollar", "promovues", "promocional", "pako festive",
    "fundvit", "furnizim me pije", "verë", "vere", "rakia", "raki",
    "gift", "promotional", "souvenir", "suvenir",
]
# =============================================================================

SEEN_FILE = Path("seen.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; tender-watch)"}


def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()


def save_seen(seen):
    SEEN_FILE.write_text(
        json.dumps(sorted(seen), ensure_ascii=False, indent=1), encoding="utf-8"
    )


def scan(name, url):
    """Return a list of (title, link) matching the keywords on one page."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"[{name}] could not fetch {url}: {e}", file=sys.stderr)
        return None  # None = failed, [] = fetched but nothing found

    soup = BeautifulSoup(r.text, "html.parser")
    found, dupes = [], set()
    for a in soup.find_all("a", href=True):
        text = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        if len(text) < 8:
            continue
        if any(k in text.lower() for k in KEYWORDS):
            link = urljoin(url, a["href"])
            if (text, link) not in dupes:
                dupes.add((text, link))
                found.append((text, link))
    return found


def send_email(subject, body):
    user = os.environ.get("EMAIL_USER")
    password = os.environ.get("EMAIL_PASSWORD")
    to = os.environ.get("EMAIL_TO") or user
    if not user or not password:
        print("EMAIL_USER / EMAIL_PASSWORD not set; printing instead:\n")
        print(subject, "\n", body)
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.set_content(body)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(user, password)
        server.send_message(msg)
    print(f"Email sent to {to}")


def main():
    seen = load_seen()
    new_items = []   # (source, title, link)
    failed = []      # sources that could not be fetched

    for name, url in SOURCES.items():
        results = scan(name, url)
        if results is None:
            failed.append(name)
            continue
        for title, link in results:
            key = f"{name}|{link}|{title}"
            if key not in seen:
                seen.add(key)
                new_items.append((name, title, link))

    if new_items:
        lines = [f"{len(new_items)} new possible tender(s) found:\n"]
        for name, title, link in new_items:
            lines.append(f"[{name}] {title}\n{link}\n")
        if failed:
            lines.append("Could not be checked this time: " + ", ".join(failed))
        send_email(f"Tender alert: {len(new_items)} new", "\n".join(lines))
    else:
        print("No new matches.")
        if failed:
            print("Could not be checked:", ", ".join(failed))

    save_seen(seen)


if __name__ == "__main__":
    main()
