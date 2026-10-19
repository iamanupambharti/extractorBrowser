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
        Uploads a PDF file using visible file picker, popup menu, or file input element.
        Waits for attachment confirmation chip with auto-approval fallback.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"PDF file does not exist: {file_path}")

        logger.info(f"Initiating upload for: {file_path.name}")
        file_dispatched = False

        # 1. Check if direct file input element exists on the page
        file_inputs = self.page.locator("input[type='file']")
        if file_inputs.count() > 0:
            try:
                file_inputs.first.set_input_files(str(file_path))
                logger.info("Attached file directly via input[type='file']")
                file_dispatched = True
            except Exception as e:
                logger.debug(f"Direct set_input_files failed: {e}")

        # 2. If not dispatched, click upload/attach button
        if not file_dispatched:
            upload_btn = self.find_first_visible(selectors.UPLOAD_BUTTON_SELECTORS, timeout_s=3.0)
            if upload_btn:
                # Try direct file chooser expectation upon clicking upload button
                try:
                    with self.page.expect_file_chooser(timeout=2000) as fc_info:
                        upload_btn.click()
                    fc_info.value.set_files(str(file_path))
                    logger.info("File uploaded via direct expect_file_chooser")
                    file_dispatched = True
                except Exception:
                    # Upload button may have opened a dropdown menu (common in Gemini)
                    logger.info("Upload button did not directly open file chooser; checking for dropdown menu items...")
                    menu_item = self.find_first_visible(selectors.UPLOAD_MENU_ITEM_SELECTORS, timeout_s=2.5)
                    if menu_item:
                        try:
                            with self.page.expect_file_chooser(timeout=5000) as fc_info:
                                menu_item.click()
                            fc_info.value.set_files(str(file_path))
                            logger.info("File uploaded via menu item expect_file_chooser")
                            file_dispatched = True
                        except Exception as m_err:
                            logger.warning(f"Menu item file chooser trigger failed: {m_err}")
                    else:
                        # Check if clicking upload button injected input[type='file'] into DOM
                        file_inputs_post = self.page.locator("input[type='file']")
                        if file_inputs_post.count() > 0:
                            try:
                                file_inputs_post.first.set_input_files(str(file_path))
                                logger.info("Attached file via input[type='file'] after button click")
                                file_dispatched = True
                            except Exception as inp_err:
                                logger.debug(f"Input file set after button click failed: {inp_err}")

        # 3. Fallback: check toolbar inside or near the composer area
        if not file_dispatched:
            try:
                composer = self.find_first_visible(selectors.COMPOSER_SELECTORS, timeout_s=2.0)
                if composer:
                    toolbar_btns = self.page.locator("rich-textarea, div[role='textbox']").locator("xpath=ancestor::*[contains(@class, 'input-area') or contains(@class, 'box') or contains(@class, 'container')]//button")
                    if toolbar_btns.count() > 0:
                        btn0 = toolbar_btns.first
                        try:
                            with self.page.expect_file_chooser(timeout=2500) as fc_info:
                                btn0.click()
                            fc_info.value.set_files(str(file_path))
                            logger.info("File uploaded via composer toolbar button")
                            file_dispatched = True
                        except Exception:
                            pass
            except Exception:
                pass

        # 4. Wait for attachment confirmation chip or filename indicator
        max_wait = min(getattr(self.cfg, "upload_timeout_s", 20), 25)
        start_wait = time.time()
        while time.time() - start_wait < max_wait:
            chip = self.find_first_visible(selectors.ATTACHMENT_CHIP_SELECTORS, timeout_s=1.0)
            if chip:
                logger.info("Attachment confirmed via attachment chip.")
                time.sleep(1)
                return True
            # Also check if filename or stem appears on the page
            try:
                name_match = self.page.locator(f"text='{file_path.name}'").first
                if name_match.is_visible(timeout=500):
                    logger.info(f"Attachment confirmed via filename match '{file_path.name}'.")
                    time.sleep(1)
                    return True
                stem_match = self.page.locator(f"text='{file_path.stem}'").first
                if stem_match.is_visible(timeout=500):
                    logger.info(f"Attachment confirmed via file stem match '{file_path.stem}'.")
                    time.sleep(1)
                    return True
            except Exception:
                pass
            time.sleep(1)

        auto_approve = getattr(self.cfg, "auto_approve_permission", True)
        if auto_approve:
            logger.info("Attachment chip not definitively detected after upload timeout. Auto-approving user permission to continue.")
            return True

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

    def get_latest_response_length(self) -> int:
        """Lightweight JavaScript evaluation to check response text length without heavy DOM traversal."""
        try:
            res = self.page.evaluate('''() => {
                const sels = [
                    'model-response',
                    'message-content',
                    '.model-response-text',
                    '.response-container',
                    '[data-test-id="model-response-text"]',
                    'div.presented-content',
                    'div.markdown'
                ];
                for (const s of sels) {
                    const els = document.querySelectorAll(s);
                    if (els.length > 0) {
                        const txt = els[els.length - 1].innerText || '';
                        if (txt.trim().length > 0) return txt.trim().length;
                    }
                }
                return 0;
            }''')
            return int(res or 0)
        except Exception:
            return 0

    def wait_for_completion(self, timeout_s: Optional[int] = None) -> bool:
        """
        Monitors generation progress until completion or timeout.
        Uses response action buttons (copy/thumbs-up), text stability, and stop-button detection.
        """
        timeout = timeout_s or self.cfg.generation_timeout_s
        logger.info(f"Waiting for generation completion (timeout={timeout}s)...")
        start_time = time.time()

        # Brief delay to allow generation state to engage
        time.sleep(2)

        last_len = 0
        stable_count = 0

        while time.time() - start_time < timeout:
            if self.check_for_usage_limit():
                raise RuntimeError("Usage limit reached on Gemini.")

            # Strict stop button check (only true stop buttons, no generic text)
            stop_btn = self.find_first_visible(selectors.STOP_GENERATION_SELECTORS, timeout_s=0.5)

            # Check for completion action buttons (Copy / Thumbs up) which Gemini only mounts once done
            completed_btn = self.find_first_visible(selectors.RESPONSE_COMPLETED_SELECTORS, timeout_s=0.5)
            if completed_btn and not stop_btn:
                logger.info("Generation confirmed complete: copy/action buttons rendered on response.")
                time.sleep(1)
                return True

            # Check text length stability
            current_len = self.get_latest_response_length()
            if current_len > 100:
                if current_len == last_len:
                    stable_count += 1
                    # If length is stable for 2 consecutive cycles (>= 6s) and no stop button is active
                    if stable_count >= 2 and not stop_btn:
                        logger.info(f"Generation confirmed complete: response text stable at {current_len} chars.")
                        time.sleep(1)
                        return True
                else:
                    stable_count = 0
                    last_len = current_len

            # Fallback check: composer idle and substantial text present
            if not stop_btn and self.is_composer_ready() and current_len > 100:
                logger.info(f"Generation complete: composer ready with {current_len} chars generated.")
                time.sleep(1)
                return True

            time.sleep(3)

        # If timeout reached, check if substantial text was generated anyway
        final_len = self.get_latest_response_length()
        if final_len > 100:
            logger.warning(
                f"Generation wait timeout reached ({timeout}s), but response text exists ({final_len} chars). Proceeding with captured text."
            )
            return True

        logger.warning(f"Generation did not complete within {timeout}s.")
        return False

    def capture_latest_response(self) -> str:
        """
        Extracts the visible text of the latest assistant response message.
        Uses direct DOM evaluation for highest speed and fidelity on large generations.
        """
        logger.info("Capturing latest model response from page...")
        # Fast direct DOM evaluation (single atomic call)
        try:
            text = self.page.evaluate('''() => {
                const sels = [
                    'model-response',
                    'message-content',
                    '.model-response-text',
                    '.response-container',
                    '[data-test-id="model-response-text"]',
                    'div.presented-content',
                    'div.markdown'
                ];
                for (const s of sels) {
                    const els = document.querySelectorAll(s);
                    if (els.length > 0) {
                        const txt = els[els.length - 1].innerText.trim();
                        if (txt.length > 0) return txt;
                    }
                }
                return "";
            }''')
            if text and len(text) > 0:
                logger.info(f"Captured response ({len(text)} chars) via direct DOM evaluation.")
                return text
        except Exception as e:
            logger.debug(f"Direct DOM evaluation had error: {e}")

        # Fallback to Playwright locators
        for sel in selectors.RESPONSE_CONTAINER_SELECTORS:
            try:
                locators = self.page.locator(sel)
                count = locators.count()
                if count > 0:
                    latest = locators.nth(count - 1)
                    text = latest.inner_text().strip()
                    if text:
                        logger.info(f"Captured response ({len(text)} chars) using selector '{sel}'.")
                        return text
            except Exception:
                continue

        # Last resort fallback: locate all paragraphs or message divs
        try:
            paragraphs = self.page.locator("div[role='region'], div.conversation-container").all_inner_texts()
            if paragraphs:
                return "\n".join(paragraphs).strip()
        except Exception:
            pass

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
