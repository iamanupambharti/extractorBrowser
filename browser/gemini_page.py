"""
Gemini Web page interaction adapter.
Handles navigation, authentication detection, file upload, prompt submission,
completion detection, and visible response extraction.
"""
from pathlib import Path
import time
from typing import Optional, List
from playwright.sync_api import Page, Locator, TimeoutError as PlaywrightTimeoutError
from core.config import config
from core.logging_config import logger
from browser import selectors

class GeminiPageAdapter:
    """Wraps Gemini web page operations with resilient locator fallbacks."""
    def __init__(self, page: Page, app_config=config):
        self.page = page
        self.cfg = app_config

    def navigate(self) -> None:
        """Navigates to Gemini home URL if not already there."""
        current_url = ""
        try:
            current_url = self.page.url
        except Exception:
            pass

        if not current_url or ("gemini.google.com" not in current_url and "accounts.google.com" not in current_url):
            logger.info(f"Navigating to Gemini: {self.cfg.gemini_url}")
            self.page.goto(self.cfg.gemini_url, wait_until="domcontentloaded")
            time.sleep(2)
        else:
            logger.info(f"Browser already on target domain: {current_url}")

    def find_first_visible(self, selector_list: List[str], timeout_s: float = 2.0) -> Optional[Locator]:
        """Tries a list of selectors in priority order and returns the first visible one."""
        for sel in selector_list:
            try:
                locator = self.page.locator(sel).first
                if locator.is_visible(timeout=int(timeout_s * 1000)):
                    return locator
            except Exception:
                continue
        return None

    def check_is_auth_required(self) -> bool:
        """Checks if page is on sign-in page or shows authentication prompts."""
        try:
            if "accounts.google.com" in self.page.url:
                logger.info("URL indicates Google authentication page.")
                return True
        except Exception:
            pass

        for sel in selectors.AUTH_INDICATORS:
            try:
                if self.page.locator(sel).first.is_visible(timeout=1000):
                    logger.warning(f"Auth indicator detected: {sel}")
                    return True
            except Exception:
                continue
        return False

    def is_composer_ready(self) -> bool:
        """Checks if prompt composer input is available."""
        composer = self.find_first_visible(selectors.COMPOSER_SELECTORS, timeout_s=2.0)
        return composer is not None

    def upload_pdf(self, file_path: Path) -> bool:
        """
        Uploads a PDF file using the visible file picker or file input element.
        Waits for attachment confirmation chip.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"PDF file does not exist: {file_path}")

        logger.info(f"Initiating upload for: {file_path.name}")

        # Check if direct file input element exists on the page
        file_inputs = self.page.locator("input[type='file']")
        if file_inputs.count() > 0:
            try:
                file_inputs.first.set_input_files(str(file_path))
                logger.info("Attached file directly via input[type='file']")
            except Exception as e:
                logger.debug(f"Direct set_input_files failed, trying file chooser: {e}")
                pass

        # If not uploaded yet, click upload/attach button with file chooser listener
        upload_btn = self.find_first_visible(selectors.UPLOAD_BUTTON_SELECTORS, timeout_s=3.0)
        if upload_btn:
            try:
                with self.page.expect_file_chooser(timeout=5000) as fc_info:
                    upload_btn.click()
                file_chooser = fc_info.value
                file_chooser.set_files(str(file_path))
                logger.info("File uploaded via expect_file_chooser")
            except Exception as e:
                logger.warning(f"File chooser trigger had warning: {e}")

        # Wait for attachment chip to appear
        start_wait = time.time()
        while time.time() - start_wait < self.cfg.upload_timeout_s:
            chip = self.find_first_visible(selectors.ATTACHMENT_CHIP_SELECTORS, timeout_s=1.0)
            if chip:
                logger.info("Attachment confirmed via attachment chip.")
                time.sleep(1)
                return True
            time.sleep(1)

        logger.warning("Attachment chip not definitively detected after upload timeout.")
        return False

    def submit_prompt(self, prompt_text: str) -> bool:
        """
        Fills the composer with prompt_text and submits it.
        """
        logger.info("Locating composer for prompt submission...")
        composer = self.find_first_visible(selectors.COMPOSER_SELECTORS, timeout_s=5.0)
        if not composer:
            raise RuntimeError("Composer textbox not found.")

        composer.click()
        time.sleep(0.5)

        # Fill text or insert text
        try:
            composer.fill(prompt_text)
        except Exception:
            # Fallback for rich-text div
            self.page.keyboard.insert_text(prompt_text)

        time.sleep(1)

        # Click send button
        send_btn = self.find_first_visible(selectors.SEND_BUTTON_SELECTORS, timeout_s=3.0)
        if send_btn and send_btn.is_enabled():
            send_btn.click()
            logger.info("Clicked send button.")
        else:
            # Fallback: Enter key
            logger.info("Send button not enabled/found, pressing Enter key.")
            self.page.keyboard.press("Enter")

        time.sleep(2)
        return True

    def check_for_usage_limit(self) -> bool:
        """Checks if a rate limit or usage limit message is rendered."""
        for sel in selectors.USAGE_LIMIT_SELECTORS:
            try:
                if self.page.locator(sel).first.is_visible(timeout=500):
                    logger.warning(f"Usage limit detected with selector: {sel}")
                    return True
            except Exception:
                continue
        return False

    def wait_for_completion(self, timeout_s: Optional[int] = None) -> bool:
        """
        Monitors generation progress until completion or timeout.
        Detects stop-generating button toggles and usage limit notices.
        """
        timeout = timeout_s or self.cfg.generation_timeout_s
        logger.info(f"Waiting for generation completion (timeout={timeout}s)...")
        start_time = time.time()

        # Brief delay to allow generation state to engage
        time.sleep(3)

        while time.time() - start_time < timeout:
            if self.check_for_usage_limit():
                raise RuntimeError("Usage limit reached on Gemini.")

            stop_btn = self.find_first_visible(selectors.STOP_GENERATION_SELECTORS, timeout_s=1.0)
            if not stop_btn:
                # If stop button is not visible, generation likely finished.
                # Double-check if send button is back or composer is active.
                if self.is_composer_ready():
                    logger.info("Generation appears complete: composer is idle and ready.")
                    time.sleep(1)
                    return True

            time.sleep(2)

        logger.warning(f"Generation did not complete within {timeout}s.")
        return False

    def capture_latest_response(self) -> str:
        """
        Extracts the visible text of the latest assistant response message.
        """
        logger.info("Capturing latest model response from page...")
        for sel in selectors.RESPONSE_CONTAINER_SELECTORS:
            locators = self.page.locator(sel)
            count = locators.count()
            if count > 0:
                latest = locators.nth(count - 1)
                text = latest.inner_text().strip()
                if text:
                    logger.info(f"Captured response ({len(text)} chars) using selector '{sel}'.")
                    return text

        # Last resort fallback: locate all paragraphs or message divs
        paragraphs = self.page.locator("div[role='region'], div.conversation-container").all_inner_texts()
        if paragraphs:
            return "\n".join(paragraphs).strip()

        raise RuntimeError("Could not isolate latest assistant response on page.")

    def take_screenshot(self, name_prefix: str = "error") -> Path:
        """Takes a diagnostic screenshot and returns path."""
        out_path = self.cfg.logs_dir / f"{name_prefix}_{int(time.time())}.png"
        try:
            self.page.screenshot(path=str(out_path), full_page=False)
            logger.info(f"Saved diagnostic screenshot to {out_path}")
        except Exception as e:
            logger.warning(f"Could not save screenshot: {e}")
        return out_path
