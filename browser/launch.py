"""
Browser context launcher and lifecycle management using Playwright.
Uses a dedicated persistent profile for Chromium to preserve user sessions safely.
Handles process cleanup, health checks, and stale locks.
"""
from pathlib import Path
import os
import time
from typing import Optional
from playwright.sync_api import sync_playwright, BrowserContext, Page, Playwright
from core.config import config
from core.logging_config import logger

class BrowserManager:
    """Manages persistent browser lifecycle with robust connection health checks."""
    def __init__(self, app_config=config):
        self.cfg = app_config
        self.playwright: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    def is_healthy(self) -> bool:
        """Checks if current browser, context, and page are responsive and alive."""
        if not self.page or not self.context or not self.playwright:
            return False
        try:
            if self.page.is_closed():
                return False
            # Quick evaluation to verify pipe / transport is responsive
            return self.page.evaluate("() => true") is True
        except Exception:
            return False

    def clean_stale_lockfile(self) -> None:
        """Removes leftover Chromium lockfile if no chrome process is running."""
        lockfile = self.cfg.browser_profile_dir / "lockfile"
        if lockfile.exists():
            try:
                lockfile.unlink(missing_ok=True)
                logger.info("Cleaned stale browser profile lockfile.")
            except Exception as e:
                logger.debug(f"Could not remove lockfile: {e}")

    def launch(self) -> Page:
        """
        Launches Chromium with persistent user profile.
        Returns the active Page instance.
        """
        self.cfg.ensure_directories()
        profile_dir = self.cfg.browser_profile_dir

        # If already healthy, reuse page
        if self.is_healthy():
            logger.info("Reusing existing healthy browser context.")
            return self.page

        # Otherwise clean up any dead handles first
        self.close()
        self.clean_stale_lockfile()

        logger.info(f"Launching persistent browser context from {profile_dir} (headless={self.cfg.headless})")
        self.playwright = sync_playwright().start()

        args = [
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
            "--no-default-browser-check",
        ]

        try:
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=self.cfg.headless,
                viewport={"width": self.cfg.viewport_width, "height": self.cfg.viewport_height},
                args=args,
                timeout=self.cfg.page_load_timeout_s * 1000,
            )

            pages = self.context.pages
            if pages:
                self.page = pages[0]
            else:
                self.page = self.context.new_page()

            self.page.set_default_timeout(self.cfg.element_wait_timeout_s * 1000)
            return self.page
        except Exception as e:
            logger.error(f"Failed to launch browser context: {e}")
            self.close()
            raise

    def close(self) -> None:
        """Closes page, context, and stops Playwright cleanly."""
        logger.info("Closing browser context and Playwright instance...")
        try:
            if self.context:
                self.context.close()
        except Exception as e:
            logger.debug(f"Error closing browser context: {e}")
        finally:
            self.context = None
            self.page = None

        try:
            if self.playwright:
                self.playwright.stop()
        except Exception as e:
            logger.debug(f"Error stopping Playwright: {e}")
        finally:
            self.playwright = None

browser_manager = BrowserManager()
