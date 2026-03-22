"""
AirMax TV Weekly Activation Code Fetcher
=========================================
Automates extracting the weekly AirMax TV activation code from VVirusLove
and sending it to a Telegram chat.

Requirements:
    uv pip install selenium requests Pillow pytesseract

Setup:
    1. Install Chrome and ChromeDriver (or use webdriver-manager)
    2. Install Tesseract OCR: https://github.com/tesseract-ocr/tesseract
    3. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID below or as environment variables
    4. Schedule with Windows Task Scheduler for weekly execution
"""

import os
import sys
import time
import logging
import requests
from datetime import datetime
from io import BytesIO

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

try:
    from PIL import Image
    import pytesseract
except ImportError:
    pytesseract = None

# ─── Configuration ───────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# URLs
FIRST_PAGE = (
    "https://www.vviruslove.com/"
    "%d8%aa%d9%81%d8%b9%d9%8a%d9%84-%d9%83%d9%88%d8%af-%d8%aa%d8%b7%d8%a8%d9%8a%d9%82"
    "-airmax-tv-%d9%84%d9%85%d8%af%d9%89-%d8%a7%d9%84%d8%ad%d9%8a%d8%a7%d9%87"
    "-%d9%84%d9%85%d8%b4%d8%a7%d9%87%d8%af%d8%a9/"
)
SECOND_PAGE = (
    "https://www.vviruslove.com/"
    "2-%d9%83%d9%88%d8%af-%d8%aa%d9%81%d8%b9%d9%8a%d9%84-code-airmax-2026-2025/"
)
FINAL_PAGE_BASE = "https://www.vviruslove.com/aaaz111aa/"

# Timer / retry settings
MAX_TIMER_WAIT_SECONDS = 120
PAGE_LOAD_WAIT = 10
MAX_RETRIES = 3

# Logging
LOG_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(LOG_DIR, "airmax_fetcher.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ─── Telegram Helper ─────────────────────────────────────────────────────────
def send_telegram_message(text: str) -> bool:
    """Send a message to the configured Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not configured. Skipping send.")
        print(f"\n>>> MESSAGE (not sent): {text}")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        logger.info("Telegram message sent successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


# ─── Browser Helpers ──────────────────────────────────────────────────────────
def create_driver() -> webdriver.Chrome:
    """Create a headless Chrome WebDriver instance."""
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--lang=ar")
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(30)
    return driver


def dismiss_popups(driver: webdriver.Chrome):
    """Try to dismiss common popups/modals on VVirusLove."""
    try:
        # Press Escape to close any modal
        from selenium.webdriver.common.keys import Keys
        body = driver.find_element(By.TAG_NAME, "body")
        body.send_keys(Keys.ESCAPE)
        time.sleep(1)
    except Exception:
        pass


def wait_for_timer(driver: webdriver.Chrome) -> bool:
    """Wait for the countdown timer on the second page to reach zero."""
    logger.info("Waiting for countdown timer to finish...")
    start = time.time()
    while time.time() - start < MAX_TIMER_WAIT_SECONDS:
        try:
            # Look for the CTA button that appears after the timer ends
            buttons = driver.find_elements(By.PARTIAL_LINK_TEXT, "اضغط هنا للحصول على الكود")
            for btn in buttons:
                if btn.is_displayed():
                    logger.info("Timer finished — CTA button is now visible.")
                    return True
            # Also check for any element with the button text
            elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'اضغط هنا للحصول على الكود')]")
            for el in elements:
                if el.is_displayed():
                    logger.info("Timer finished — CTA element is now visible.")
                    return True
        except Exception:
            pass
        time.sleep(2)

    logger.warning("Timer did not finish within the expected time.")
    return False


def extract_code_from_page(driver: webdriver.Chrome) -> str | None:
    """Extract the activation code from the final page text or image."""
    # Method 1: Try to find the code in page text
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text
        # Look for patterns like "كود التفعيل: XXXXXXXXXX" or just a 10-digit number
        import re
        # Search for "كود التفعيل" followed by digits
        match = re.search(r"كود التفعيل[:\s]*(\d{6,12})", page_text)
        if match:
            code = match.group(1)
            logger.info(f"Code found in page text: {code}")
            return code

        # Search for standalone large numbers (likely the code)
        matches = re.findall(r"\b(\d{8,12})\b", page_text)
        if matches:
            code = matches[0]
            logger.info(f"Code found as number in text: {code}")
            return code
    except Exception as e:
        logger.warning(f"Text extraction failed: {e}")

    # Method 2: Try to read the code from an image using OCR
    if pytesseract:
        try:
            images = driver.find_elements(By.TAG_NAME, "img")
            for img in images:
                src = img.get_attribute("src")
                if not src or "logo" in src.lower() or "icon" in src.lower():
                    continue
                # Check if the image is large enough to contain a code
                width = img.size.get("width", 0)
                height = img.size.get("height", 0)
                if width < 200 or height < 100:
                    continue

                logger.info(f"Attempting OCR on image: {src[:80]}...")
                # Download the image
                if src.startswith("data:"):
                    continue
                resp = requests.get(src, timeout=10)
                pil_img = Image.open(BytesIO(resp.content))
                text = pytesseract.image_to_string(pil_img, config="--psm 6 digits")
                import re
                numbers = re.findall(r"\d{6,12}", text)
                if numbers:
                    code = numbers[0]
                    logger.info(f"Code found via OCR: {code}")
                    return code
        except Exception as e:
            logger.warning(f"OCR extraction failed: {e}")

    # Method 3: Check alt text of images
    try:
        images = driver.find_elements(By.TAG_NAME, "img")
        import re
        for img in images:
            alt = img.get_attribute("alt") or ""
            match = re.search(r"\d{6,12}", alt)
            if match:
                code = match.group(0)
                logger.info(f"Code found in image alt text: {code}")
                return code
    except Exception as e:
        logger.warning(f"Alt text extraction failed: {e}")

    return None


# ─── Main Flow ────────────────────────────────────────────────────────────────
def fetch_airmax_code() -> str | None:
    """
    Full flow:
    1. Navigate to first page
    2. Find and follow the "official codes" link
    3. Wait for the countdown timer
    4. Click the CTA button
    5. Extract the code from the final page
    """
    driver = create_driver()
    code = None

    try:
        # Step 1: Go to the second page directly (more reliable than
        # navigating through the first page which has ad popups)
        logger.info(f"Navigating to codes page: {SECOND_PAGE}")
        driver.get(SECOND_PAGE)
        time.sleep(PAGE_LOAD_WAIT)
        dismiss_popups(driver)

        # Step 2: Check if the "official codes" button still exists
        # (safety check for site structure changes)
        page_source = driver.page_source
        if "اضغط هنا للحصول على الكود" not in page_source and "الكود" not in page_source:
            logger.error("SAFETY CHECK FAILED: The site structure may have changed. "
                         "The expected code button was not found.")
            send_telegram_message(
                "⚠️ AirMax TV code extraction failed.\n"
                "The VVirusLove website structure appears to have changed.\n"
                "Manual check required."
            )
            return None

        # Step 3: Wait for the countdown timer
        timer_done = wait_for_timer(driver)

        if timer_done:
            # Click the CTA button
            try:
                btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//*[contains(text(), 'اضغط هنا للحصول على الكود')]")
                    )
                )
                btn.click()
                logger.info("Clicked CTA button. Waiting for redirect...")
                time.sleep(PAGE_LOAD_WAIT)
            except TimeoutException:
                logger.warning("CTA button not clickable. Trying direct navigation.")
                driver.get(FINAL_PAGE_BASE)
                time.sleep(PAGE_LOAD_WAIT)
        else:
            # Timer didn't finish — try navigating directly
            logger.info("Bypassing timer — navigating directly to final page.")
            driver.get(FINAL_PAGE_BASE)
            time.sleep(PAGE_LOAD_WAIT)

        # Step 4: Dismiss any popups on the final page
        dismiss_popups(driver)
        time.sleep(2)

        # Step 5: Extract the code
        code = extract_code_from_page(driver)

        if code:
            logger.info(f"✅ Successfully extracted code: {code}")
        else:
            logger.warning("❌ Could not extract the code from the final page.")
            # Take a screenshot for debugging
            screenshot_path = os.path.join(LOG_DIR, f"debug_{datetime.now():%Y%m%d_%H%M%S}.png")
            driver.save_screenshot(screenshot_path)
            logger.info(f"Debug screenshot saved to: {screenshot_path}")

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
    finally:
        driver.quit()

    return code


def main():
    logger.info("=" * 60)
    logger.info("AirMax TV Code Fetcher — Starting")
    logger.info(f"Date: {datetime.now():%Y-%m-%d %H:%M:%S}")
    logger.info("=" * 60)

    code = None
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"Attempt {attempt}/{MAX_RETRIES}...")
        code = fetch_airmax_code()
        if code:
            break
        if attempt < MAX_RETRIES:
            logger.info("Retrying in 30 seconds...")
            time.sleep(30)

    if code:
        message = f"AirMax TV weekly code: {code}"
        print(f"\n{'='*40}")
        print(f"  {message}")
        print(f"{'='*40}\n")
        send_telegram_message(message)
    else:
        message = "AirMax TV weekly code could not be extracted."
        print(f"\n⚠️ {message}")
        send_telegram_message(message)

    logger.info("Done.\n")


if __name__ == "__main__":
    main()
