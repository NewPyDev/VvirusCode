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
sys.stdout.reconfigure(encoding='utf-8')
import logging
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright
from pathlib import Path
import time

# File to persist the last fetched code (lives next to this script)
SCRIPT_DIR = Path(__file__).resolve().parent
LAST_CODE_FILE = SCRIPT_DIR / "last_code.txt"

# ─── Configuration ───────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# The final page that contains the activation code directly
CODE_PAGE_URL = "https://www.vviruslove.com/%d8%aa%d9%81%d8%b9%d9%8a%d9%84-%d9%83%d9%88%d8%af-%d8%aa%d8%b7%d8%a8%d9%8a%d9%82-airmax-tv-%d9%84%d9%85%d8%af%d9%89-%d8%a7%d9%84%d8%ad%d9%8a%d8%a7%d9%87-%d9%84%d9%85%d8%b4%d8%a7%d9%87%d8%af%d8%a9/"

# Fallback: the intermediate page (codes listing)
CODES_LIST_URL = (
    "https://www.vviruslove.com/"
    "2-%d9%83%d9%88%d8%af-%d8%aa%d9%81%d8%b9%d9%8a%d9%84-code-airmax-2026-2025-2/"
)

MAX_RETRIES     = 3
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

def extract_code_from_html(html: str) -> str | None:
    """
    Extract the activation code from page HTML using multiple strategies:

    1. Image filename scoped to the CURRENT month  ← BUG FIX
       (e.g. /uploads/2026/04/6597416103.jpg)
    2. Text pattern near  "كود التفعيل"
    3. Any standalone 8-12 digit number in the relevant section
    """

    now   = datetime.now()
    year  = now.strftime("%Y")   # e.g. "2026"
    month = now.strftime("%m")   # e.g. "04"

    # ── Strategy 1 (FIXED): Image filename scoped to current month ────────────
    # Previously used \d{4}/\d{2}/ which matched ANY month, so it always
    # returned the first (often outdated) image found in the page HTML.
    # Now we pin to the current year/month so we only pick up this week's image.
    pattern_img = rf"/uploads/{year}/\d{{2}}/(\d{{8,12}})\.(?:jpg|png|webp|avif)"
    match = re.search(pattern_img, html)
    if match:
        code = match.group(1)
        logger.info(f"Code found in image filename ({year}/{month}): {code}")
        return code
    else:
        logger.warning(
            f"Strategy 1: no image found under /uploads/{year}/. "
            "Falling back to other strategies."
        )

    # ── Strategy 2: "كود التفعيل" followed by digits ─────────────────────────
    match = re.search(r"كود[_ ]التفعيل[:\s]*(\d{6,12})", html)
    if match:
        code = match.group(1)
        logger.info(f"Code found near 'كود التفعيل': {code}")
        return code

    # ── Strategy 3: تحميل الكود link with code in URL ────────────────────────
    match = re.search(r"تحميل الكود.*?(\d{8,12})", html, re.DOTALL)
    if match:
        code = match.group(1)
        logger.info(f"Code found in download link: {code}")
        return code

    # ── Strategy 4: Any 10-digit number in the code section ──────────────────
    code_section = re.search(
        r"تم تجهيز كود التفعيل(.{0,2000})",
        html,
        re.DOTALL,
    )
    if code_section:
        numbers = re.findall(r"\b(\d{10})\b", code_section.group(1))
        if numbers:
            code = numbers[0]
            logger.info(f"Code found as 10-digit number: {code}")
            return code

    return None

# ─── Fetcher ──────────────────────────────────────────────────────────────────

def fetch_code() -> str | None:
    """Fetch the activation code from VVirusLove using Playwright."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            # Disable cache so we always get fresh content
            context = browser.new_context()
            context.set_extra_http_headers({"Cache-Control": "no-cache, no-store", "Pragma": "no-cache"})
            page = context.new_page()

            logger.info(f"Navigating to Codes list: {CODES_LIST_URL}")
            page.goto(CODES_LIST_URL, wait_until='networkidle', timeout=60000)

            logger.info("Waiting 35 seconds for the countdown...")
            for _ in range(35):
                page.evaluate("window.scrollBy(0, 200)")
                page.wait_for_timeout(1000)

            # ── Attempt 1: click button and catch the popup tab ──────────
            loc = page.locator('.cta-pro')
            popup_page = None
            if loc.count() > 0:
                logger.info("Found .cta-pro button — clicking with expect_popup...")
                try:
                    with context.expect_page(timeout=15000) as popup_info:
                        loc.first.click(force=True)
                    popup_page = popup_info.value
                    popup_page.wait_for_load_state('networkidle', timeout=15000)
                    logger.info(f"Popup opened: {popup_page.url}")
                except Exception as e:
                    logger.warning(f"Popup did not open: {e}")

            # ── Attempt 2: extract redirect URL from page JS / HTML ──────
            if popup_page is None:
                logger.info("Trying to extract redirect URL from page source...")
                redirect_url = page.evaluate("""() => {
                    // Look for the target URL in onclick handlers or href attributes
                    var btn = document.querySelector('.cta-pro');
                    if (btn) {
                        var onclick = btn.getAttribute('onclick') || '';
                        var m = onclick.match(/https?:\\/\\/[^'"\\s]+/);
                        if (m) return m[0];
                    }
                    // Search all scripts for the redirect URL pattern
                    var scripts = document.querySelectorAll('script');
                    for (var i = 0; i < scripts.length; i++) {
                        var t = scripts[i].textContent || '';
                        var m = t.match(/https?:\\/\\/www\\.vviruslove\\.com\\/[a-z0-9]+\\/\\?utm_source=airmax/);
                        if (m) return m[0];
                    }
                    return null;
                }""")
                if redirect_url:
                    logger.info(f"Found redirect URL in page source: {redirect_url}")
                    popup_page = context.new_page()
                    popup_page.goto(redirect_url, wait_until='networkidle', timeout=30000)
                else:
                    logger.warning("Could not extract redirect URL from page source.")

            # ── Check all tabs for the code ──────────────────────────────
            for pg in context.pages:
                logger.info(f"Checking tab for code: {pg.url}")
                html = pg.content()
                code = extract_code_from_html(html)
                if code:
                    browser.close()
                    return code

            logger.warning("No code found in any tab.")
            browser.close()
            return None
    except Exception as e:
        logger.error(f"Failed during Playwright execution: {e}")
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
    logger.info("AirMax TV Code Fetcher — Starting")
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
            logger.info("Retrying in 15 seconds...")
            time.sleep(15)

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
            f"The website may not have updated. Check manually:\n{CODES_LIST_URL}"
        )
        print(f"\n  {message}")
        send_telegram_message(message)
    else:
        # New code! Save it and send it.
        save_last_code(code)
        message = f"AirMax TV weekly code: {code}"
        print(f"\n{'='*40}")
        print(f" {message}")
        print(f"{'='*40}\n")
        send_telegram_message(message)

    logger.info("Done.")


if __name__ == "__main__":
    main()
