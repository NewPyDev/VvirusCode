"""
AirMax TV Weekly Activation Code Fetcher
=========================================
Extracts the weekly AirMax TV activation code from VVirusLove
and sends it to Telegram.

Requirements:
    uv pip install requests beautifulsoup4

No browser/Selenium needed — the code is embedded in the page HTML.
"""

import os
import re
import sys
import logging
import requests
from datetime import datetime

# ─── Configuration ───────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# The final page that contains the activation code directly
CODE_PAGE_URL = "https://www.vviruslove.com/aaaz111aa/"

# Fallback: the intermediate page (codes listing)
CODES_LIST_URL = (
    "https://www.vviruslove.com/"
    "2-%d9%83%d9%88%d8%af-%d8%aa%d9%81%d8%b9%d9%8a%d9%84-code-airmax-2026-2025/"
)

MAX_RETRIES = 3
REQUEST_TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ar,en;q=0.9",
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

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        logger.info("✅ Telegram message sent successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


# ─── Code Extraction ──────────────────────────────────────────────────────────
def extract_code_from_html(html: str) -> str | None:
    """
    Extract the activation code from page HTML using multiple strategies:
    1. Image filename pattern (e.g. /uploads/2026/03/6597416103.jpg)
    2. Text pattern near "كود التفعيل"
    3. Any standalone 8-12 digit number in the relevant section
    """
    # Strategy 1: Code in image filename — most reliable
    # Pattern: /uploads/YYYY/MM/XXXXXXXXXX.jpg
    match = re.search(r"/uploads/\d{4}/\d{2}/(\d{8,12})\.(?:jpg|png|webp)", html)
    if match:
        code = match.group(1)
        logger.info(f"✅ Code found in image filename: {code}")
        return code

    # Strategy 2: "كود التفعيل" followed by digits (in text or alt attributes)
    match = re.search(r"كود[_ ]التفعيل[:\s]*(\d{6,12})", html)
    if match:
        code = match.group(1)
        logger.info(f"✅ Code found near 'كود التفعيل': {code}")
        return code

    # Strategy 3: Look for تحميل الكود link with code in URL
    match = re.search(r"تحميل الكود.*?(\d{8,12})", html, re.DOTALL)
    if match:
        code = match.group(1)
        logger.info(f"✅ Code found in download link: {code}")
        return code

    # Strategy 4: Any 10-digit number (common code format)
    # Narrow scope to the code section of the page
    code_section = re.search(
        r"تم تجهيز كود التفعيل(.{0,2000})",
        html,
        re.DOTALL,
    )
    if code_section:
        numbers = re.findall(r"\b(\d{10})\b", code_section.group(1))
        if numbers:
            code = numbers[0]
            logger.info(f"✅ Code found as 10-digit number: {code}")
            return code

    return None


def fetch_code() -> str | None:
    """Fetch the activation code from VVirusLove."""
    session = requests.Session()
    session.headers.update(HEADERS)

    # Try final page directly first (fastest)
    for url_label, url in [("Final page", CODE_PAGE_URL), ("Codes list", CODES_LIST_URL)]:
        try:
            logger.info(f"Fetching {url_label}: {url}")
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            logger.info(f"Got {len(resp.text)} chars from {url_label}")

            code = extract_code_from_html(resp.text)
            if code:
                return code
            else:
                logger.warning(f"No code found on {url_label}.")
        except Exception as e:
            logger.error(f"Failed to fetch {url_label}: {e}")

    return None


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    logger.info("=" * 50)
    logger.info("AirMax TV Code Fetcher — Starting")
    logger.info(f"Date: {datetime.now():%Y-%m-%d %H:%M:%S}")
    logger.info("=" * 50)

    code = None
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"Attempt {attempt}/{MAX_RETRIES}...")
        code = fetch_code()
        if code:
            break
        if attempt < MAX_RETRIES:
            import time
            logger.info("Retrying in 15 seconds...")
            time.sleep(15)

    if code:
        message = f"AirMax TV weekly code: {code}"
        print(f"\n{'='*40}")
        print(f"  {message}")
        print(f"{'='*40}\n")
        send_telegram_message(message)
    else:
        message = "AirMax TV weekly code could not be extracted."
        print(f"\n⚠️ {message}")
        send_telegram_message(f"⚠️ {message}\nManual check required at: {CODE_PAGE_URL}")

    logger.info("Done.")


if __name__ == "__main__":
    main()
