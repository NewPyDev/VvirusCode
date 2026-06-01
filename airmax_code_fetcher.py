"""
AirMax TV Weekly Activation Code Fetcher
=========================================
Extracts the weekly AirMax TV activation code from VVirusLove
using the WordPress REST API (no browser needed).

The real activation code lives on a weekly-rotating WordPress PAGE
(not a post) with a dynamic slug (e.g., 'aaaaa22aaa3a').
The code is embedded as an image filename: /uploads/2026/04/4985088380.jpg

This script discovers the page via the WP pages API, then extracts
the code from the image filename in the page content.

Requirements:
    pip install requests beautifulsoup4
"""

import os
import re
import sys
import json
sys.stdout.reconfigure(encoding='utf-8')
import logging
import requests
from datetime import datetime, timezone
from pathlib import Path
import time

# File to persist the last fetched code (lives next to this script)
SCRIPT_DIR = Path(__file__).resolve().parent
LAST_CODE_FILE = SCRIPT_DIR / "last_code.txt"

# ─── Configuration ───────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# WordPress REST API endpoints
# The activation code is on a PAGE (not a post) with a weekly-rotating slug.
# We fetch recent pages sorted by modification date to find the current one.
WP_PAGES_API = (
    "https://www.vviruslove.com/wp-json/wp/v2/pages"
    "?per_page=50&orderby=modified&order=desc"
    "&_fields=id,title,date,modified,link,slug,content"
)

# Known page IDs to fetch directly as fallback (the dynamic weekly pages)
# These are updated each time the site restructures
KNOWN_PAGE_IDS = [26520, 26519, 26521]  # aaaaa2222a, zzzz11111z, oooo3333oo pages
WP_PAGE_BY_ID = (
    "https://www.vviruslove.com/wp-json/wp/v2/pages/{page_id}"
    "?_fields=id,title,date,modified,link,slug,content"
)

# Direct page URL (used only in Telegram messages for manual reference)
CODE_PAGE_URL = (
    "https://www.vviruslove.com/"
    "2-%d9%83%d9%88%d8%af-%d8%aa%d9%81%d8%b9%d9%8a%d9%84-code-airmax-2026-2025/"
)

MAX_RETRIES     = 3
REQUEST_TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ar,en;q=0.9",
    "Accept": "application/json",
}

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ─── Telegram ─────────────────────────────────────────────────────────────────

def send_telegram_message(text: str) -> bool:
    """Send a message to the configured Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not configured. Skipping send.")
        print(f"\n>>> MESSAGE (not sent):\n{text}")
        return False

    url     = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}

    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        logger.info("Telegram message sent successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False

# ─── Code Extraction ──────────────────────────────────────────────────────────

def extract_activation_code(html: str) -> dict | None:
    """
    Extract both AirMax TV and AirMax TV Pro activation codes.
    Returns a dict with 'airmax' and 'pro' keys.
    """
    codes = {'airmax': None, 'pro': None}

    # ── Extract AirMax TV code ─────────────────────
    airmax_match = re.search(
        r'كود التفعيل الخاص بك airMAX[^a-zA-Z].*?'
        r'src=[\"\']https?://(?:www\.)?vviruslove\.com/wp-content/uploads/\d{4}/\d{2}/([^\"\']+)\.(?:jpg|jpeg|png|webp|avif)[\"\']',
        html,
        re.DOTALL | re.IGNORECASE
    )
    if airmax_match:
        codes['airmax'] = airmax_match.group(1)
        logger.info(f"AirMax TV Code found: {codes['airmax']}")
    else:
        # Fallback 1: Any code image
        fallback = re.search(r'/uploads/\d{4}/\d{2}/(\d{6,12})\.(?:jpg|jpeg|png|webp|avif)', html)
        if fallback:
            codes['airmax'] = fallback.group(1)
            logger.info(f"AirMax TV Code found via fallback: {codes['airmax']}")

    # ── Extract AirMax TV PRO code ─────────────────
    pro_match = re.search(
        r'كود التفعيل الخاص بك airMAX Pro.*?'
        r'src=[\"\']https?://(?:www\.)?vviruslove\.com/wp-content/uploads/\d{4}/\d{2}/([^\"\']+)\.(?:jpg|jpeg|png|webp|avif)[\"\']',
        html,
        re.DOTALL | re.IGNORECASE
    )
    if pro_match:
        codes['pro'] = pro_match.group(1)
        logger.info(f"AirMax TV PRO Code found: {codes['pro']}")
    else:
        # Fallback for PRO (often alphanumeric like 3C08EC)
        fallback_pro = re.findall(r'/uploads/\d{4}/\d{2}/([A-Za-z0-9]{4,12})\.(?:jpg|jpeg|png|webp|avif)', html)
        for m in fallback_pro:
            if m.lower() not in ('screenshot_1', 'activation-code') and not m.isdigit():
                codes['pro'] = m
                logger.info(f"AirMax TV PRO Code found via fallback: {codes['pro']}")
                break

    # If we found at least one code, return the dict.
    if codes['airmax'] or codes['pro']:
        return codes

    return None

def is_activation_page(title: str, content: str) -> bool:
    """Check if a WordPress page is the weekly activation code page for AirMax TV."""
    # Filter by TITLE only — the content often has cross-promotion links
    # to OTTPlayer, SS Player, etc. that would cause false negatives.
    title_lower = title.lower()
    if 'ottplayer' in title_lower or 'ss player' in title_lower or 'airmax live' in title_lower:
        return False

    # The AirMax LIVE page uses "airMAX LIVE" in the activation heading
    # (e.g. "كود التفعيل الخاص بك airMAX LIVE"), so exclude those too.
    if re.search(r'كود التفعيل الخاص بك airMAX\s+LIVE', content, re.IGNORECASE):
        return False
        
    markers = [
        'كود التفعيل الخاص بك airMAX',  # "Your airMAX activation code"
        'هذا الكود خاص فقط لتطبيق AirMaxTV',  # "This code is only for AirMaxTV"
    ]
    return any(marker in content for marker in markers)

# ─── Fetcher ──────────────────────────────────────────────────────────────────

def _scan_pages(pages: list) -> dict | None:
    """Scan a list of WP page dicts for the activation code page."""
    for page in pages:
        page_id  = page.get("id", "?")
        title    = page.get("title", {}).get("rendered", "No title")
        slug     = page.get("slug", "")
        modified = page.get("modified", "")
        link     = page.get("link", "")
        content  = page.get("content", {}).get("rendered", "")

        if not content:
            logger.debug(f"  Page #{page_id} ({slug}): no content, skipping.")
            continue

        # Check if this page is the activation code page
        if not is_activation_page(title, content):
            logger.debug(f"  Page #{page_id} ({slug}): not an activation page.")
            continue

        logger.info(f"  >>> Found activation page!")
        logger.info(f"      Page #{page_id}: {title}")
        logger.info(f"      Slug: {slug}")
        logger.info(f"      Modified: {modified}")
        logger.info(f"      Link: {link}")

        codes = extract_activation_code(content)
        if codes:
            logger.info(f"  >>> Extracted activation codes: {codes}")
            return codes
        else:
            logger.warning(f"  Page #{page_id} matched markers but no code found in images.")

    return None


def fetch_code() -> dict | None:
    """
    Fetch the activation codes from VVirusLove using the WordPress REST API.
    Tries two strategies:
      1. Fetch recent pages sorted by modification date.
      2. Fetch known page IDs directly (fallback).
    """
    # ── Strategy 1: Bulk fetch recent pages ────────────────────────
    logger.info(f"Strategy 1: Querying WordPress Pages API (recent pages)...")

    try:
        resp = requests.get(WP_PAGES_API, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        pages = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.error(f"API request failed: {e}")
        pages = []

    if pages:
        logger.info(f"API returned {len(pages)} page(s). Scanning for activation code page...")
        codes = _scan_pages(pages)
        if codes:
            return codes
        logger.warning("No activation code found in recent pages.")
    else:
        logger.warning("API returned no pages or request failed.")

    # ── Strategy 2: Fetch known page IDs directly ─────────────────
    logger.info(f"Strategy 2: Fetching known page IDs directly: {KNOWN_PAGE_IDS}")

    for pid in KNOWN_PAGE_IDS:
        url = WP_PAGE_BY_ID.format(page_id=pid)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            page = resp.json()
        except (requests.RequestException, ValueError) as e:
            logger.warning(f"  Failed to fetch page {pid}: {e}")
            continue

        # Wrap in a list for _scan_pages
        codes = _scan_pages([page])
        if codes:
            return codes

    logger.warning("No activation code page found in any strategy.")
    return None

# ─── Main ─────────────────────────────────────────────────────────────────────

def load_last_code() -> dict | None:
    """Load the previously fetched code(s) from disk."""
    try:
        if LAST_CODE_FILE.exists():
            content = LAST_CODE_FILE.read_text().strip()
            if content:
                # Handle old format (just string '4985088380') or new JSON format
                if "{" in content:
                    return json.loads(content)
                else:
                    return {'airmax': content, 'pro': None}
    except Exception as e:
        logger.warning(f"Could not read last code file: {e}")
    return None


def save_last_code(codes: dict) -> None:
    """Persist the fetched code(s) to disk for next-run comparison."""
    try:
        content = json.dumps(codes)
        LAST_CODE_FILE.write_text(content)
        logger.info(f"Saved codes to {LAST_CODE_FILE}")
    except Exception as e:
        logger.warning(f"Could not save last code file: {e}")


def main():
    logger.info("=" * 50)
    logger.info("AirMax TV Code Fetcher — Starting (API mode)")
    logger.info(f"Date: {datetime.now():%Y-%m-%d %H:%M:%S}")
    logger.info("=" * 50)

    previous_codes = load_last_code()

    codes = None
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"Attempt {attempt}/{MAX_RETRIES}...")
        codes = fetch_code()
        if codes:
            break
        if attempt < MAX_RETRIES:
            logger.info("Retrying in 10 seconds...")
            time.sleep(10)

    # The workflow runs 3 times: Sun 03:00, Sun 12:00, Mon 03:00 UTC.
    # Only send failure/unchanged alerts on the LAST attempt (Monday).
    # New codes are sent immediately on whichever run finds them.
    is_last_attempt = datetime.now(timezone.utc).weekday() == 0  # 0 = Monday

    if not codes:
        message = "AirMax TV weekly code(s) could not be extracted."
        logger.warning(message)
        if is_last_attempt:
            send_telegram_message(
                f"WARNING: {message}\nManual check required at: {CODE_PAGE_URL}"
            )
        else:
            logger.info("Not the last scheduled attempt — will retry on next run.")
    elif codes == previous_codes:
        logger.info(f"Codes unchanged: {codes}")
        if is_last_attempt:
            message = (
                f"WARNING: AirMax TV codes have NOT changed yet.\n"
                f"AirMax TV: {codes.get('airmax', 'N/A')}\n"
                f"AirMax Pro: {codes.get('pro', 'N/A')}\n\n"
                f"The website may not have updated. Check manually:\n{CODE_PAGE_URL}"
            )
            send_telegram_message(message)
        else:
            logger.info("Not the last scheduled attempt — will retry on next run.")
    else:
        # New code! Save it and send it.
        save_last_code(codes)
        airmax_msg = codes.get('airmax') or "N/A"
        pro_msg = codes.get('pro') or "N/A"
        
        message = (
            f"🎉 New AirMax Codes Released! 🎉\n\n"
            f"📺 AirMax TV: {airmax_msg}\n"
            f"🌟 AirMax PRO: {pro_msg}\n\n"
            f"Enjoy your free shows! 🎬"
        )
        
        print(f"\n{'='*40}")
        print(message)
        print(f"{'='*40}\n")
        send_telegram_message(message)

    logger.info("Done.")


if __name__ == "__main__":
    main()
