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
sys.stdout.reconfigure(encoding='utf-8')
import logging
import requests
from datetime import datetime
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
    "?per_page=20&orderby=modified&order=desc"
    "&_fields=id,title,date,modified,link,slug,content"
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
        print(f"\n>>> MESSAGE (not sent): {text}")
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

def extract_activation_code(html: str) -> str | None:
    """
    Extract the REAL activation code from the weekly code page HTML.
    
    The code is embedded as an image filename in the page content.
    Pattern: /uploads/YYYY/MM/<CODE>.jpg
    
    The first image after "تم تجهيز كود التفعيل الخاص بك airMAX" is the AirMax TV code.
    """
    
    # ── Strategy 1: Image filename in the airMAX section ─────────────────────
    # Look for the first code image after the airMAX heading (not airMAX Pro)
    airmax_section = re.search(
        r'تم تجهيز كود التفعيل الخاص بك airMAX</h1>.*?'
        r'src=\\"https?://www\.vviruslove\.com/wp-content/uploads/(\d{4})/(\d{2})/([^"\\]+)\.jpg\\"',
        html,
        re.DOTALL,
    )
    if airmax_section:
        code = airmax_section.group(3)
        logger.info(f"Code found in airMAX section image: {code}")
        return code

    # ── Strategy 2: Any activation code image in current year ────────────────
    now = datetime.now()
    year = now.strftime("%Y")
    # Match image filenames that are pure digits (the activation code)
    pattern = rf'/uploads/{year}/\d{{2}}/(\d{{6,12}})\.jpg'
    matches = re.findall(pattern, html)
    if matches:
        code = matches[0]
        logger.info(f"Code found in image filename ({year}): {code}")
        return code

    # ── Strategy 3: Any image filename that looks like a code ────────────────
    # Some codes may be alphanumeric (e.g., "3C08EC" for Pro)
    pattern_any = rf'/uploads/{year}/\d{{2}}/([A-Za-z0-9]{{4,12}})\.jpg'
    matches = re.findall(pattern_any, html)
    if matches:
        # Filter out known non-code filenames
        for m in matches:
            if m.lower() not in ('screenshot_1', 'activation-code'):
                code = m
                logger.info(f"Code found in image filename (alphanumeric): {code}")
                return code

    # ── Strategy 4: Fallback — look for "كود التفعيل" text near digits ───────
    match = re.search(r'كود التفعيل.*?(\d{6,12})', html, re.DOTALL)
    if match:
        code = match.group(1)
        logger.info(f"Code found near 'كود التفعيل' text: {code}")
        return code

    return None


def is_activation_page(content: str) -> bool:
    """Check if a WordPress page is the weekly activation code page."""
    # The activation page contains this distinctive heading
    markers = [
        'تم تجهيز كود التفعيل',      # "Activation code has been prepared"
        'كود التفعيل الخاص بك airMAX',  # "Your airMAX activation code"
        'هذا الكود خاص فقط لتطبيق AirMaxTV',  # "This code is only for AirMaxTV"
    ]
    return any(marker in content for marker in markers)

# ─── Fetcher ──────────────────────────────────────────────────────────────────

def fetch_code() -> str | None:
    """
    Fetch the activation code from VVirusLove using the WordPress REST API.
    
    The real code lives on a weekly-rotating WordPress PAGE (not post)
    with a dynamic slug. We find it by scanning recent pages for the
    activation code section, then extract the code from the image filename.
    """
    logger.info(f"Querying WordPress Pages API: {WP_PAGES_API}")

    try:
        resp = requests.get(WP_PAGES_API, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"API request failed: {e}")
        return None

    try:
        pages = resp.json()
    except ValueError as e:
        logger.error(f"Failed to parse API response as JSON: {e}")
        return None

    if not pages:
        logger.warning("API returned no pages.")
        return None

    logger.info(f"API returned {len(pages)} page(s). Scanning for activation code page...")

    for page in pages:
        page_id  = page.get("id", "?")
        title    = page.get("title", {}).get("rendered", "No title")
        slug     = page.get("slug", "")
        modified = page.get("modified", "")
        link     = page.get("link", "")
        content  = page.get("content", {}).get("rendered", "")

        if not content:
            continue

        # Check if this page is the activation code page
        if not is_activation_page(content):
            continue

        logger.info(f"  >>> Found activation page!")
        logger.info(f"      Page #{page_id}: {title}")
        logger.info(f"      Slug: {slug}")
        logger.info(f"      Modified: {modified}")
        logger.info(f"      Link: {link}")
        logger.info(f"      Content length: {len(content)} chars")

        code = extract_activation_code(content)
        if code:
            logger.info(f"  >>> Extracted activation code: {code}")
            return code
        else:
            logger.warning(f"  Page #{page_id} matched markers but no code found in images.")

    logger.warning("No activation code page found in recent pages.")
    return None

# ─── Main ─────────────────────────────────────────────────────────────────────

def load_last_code() -> str | None:
    """Load the previously fetched code from disk."""
    try:
        if LAST_CODE_FILE.exists():
            code = LAST_CODE_FILE.read_text().strip()
            if code:
                logger.info(f"Last saved code: {code}")
                return code
    except Exception as e:
        logger.warning(f"Could not read last code file: {e}")
    return None


def save_last_code(code: str) -> None:
    """Persist the fetched code to disk for next-run comparison."""
    try:
        LAST_CODE_FILE.write_text(code)
        logger.info(f"Saved code to {LAST_CODE_FILE}")
    except Exception as e:
        logger.warning(f"Could not save last code file: {e}")


def main():
    logger.info("=" * 50)
    logger.info("AirMax TV Code Fetcher — Starting (API mode)")
    logger.info(f"Date: {datetime.now():%Y-%m-%d %H:%M:%S}")
    logger.info("=" * 50)

    previous_code = load_last_code()

    code = None
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"Attempt {attempt}/{MAX_RETRIES}...")
        code = fetch_code()
        if code:
            break
        if attempt < MAX_RETRIES:
            logger.info("Retrying in 10 seconds...")
            time.sleep(10)

    if not code:
        message = "AirMax TV weekly code could not be extracted."
        print(f"\n  {message}")
        send_telegram_message(
            f"WARNING: {message}\nManual check required at: {CODE_PAGE_URL}"
        )
    elif code == previous_code:
        logger.warning(f"Code {code} is the SAME as last week!")
        message = (
            f"WARNING: AirMax TV code has NOT changed yet ({code}).\n"
            f"The website may not have updated. Check manually:\n{CODE_PAGE_URL}"
        )
        print(f"\n  {message}")
        send_telegram_message(message)
    else:
        # New code! Save it and send it.
        save_last_code(code)
        message = f"AirMax TV weekly code: {code}"
        print(f"\n{'='*40}")
        print(f"  {message}")
        print(f"{'='*40}\n")
        send_telegram_message(message)

    logger.info("Done.")


if __name__ == "__main__":
    main()
