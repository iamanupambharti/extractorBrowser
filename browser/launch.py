"""
Browser context launcher and lifecycle management using Playwright.
Uses a dedicated persistent profile for Chromium to preserve user sessions safely.
Handles process cleanup, health checks, and stale locks.
"""
import psutil
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

    def kill_stale_chrome_processes(self) -> None:
        """Kills any orphaned chrome processes associated with our dedicated user profile."""
        profile_path = str(self.cfg.browser_profile_dir).lower()
        killed_any = False
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                name = proc.info.get('name') or ''
                if name.lower() in ('chrome.exe', 'chromium.exe'):
                    cmdline = " ".join(proc.info.get('cmdline') or []).lower()
                    if profile_path in cmdline:
                        logger.warning(f"Killing stale Chrome process {proc.info['pid']} using dedicated profile.")
                        proc.kill()
                        killed_any = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if killed_any:
            time.sleep(1)

    def clean_stale_lockfile(self) -> None:
        """Removes leftover Chromium lockfiles if no chrome process is running."""
        lockfiles = ["lockfile", "SingletonLock", "SingletonCookie", "SingletonSocket"]
        for fname in lockfiles:
            target = self.cfg.browser_profile_dir / fname
            if target.exists():
                try:
                    target.unlink(missing_ok=True)
                    logger.info(f"Cleaned stale browser profile lock: {fname}")
                except Exception as e:
                    logger.debug(f"Could not remove {fname}: {e}")

    def _apply_stealth(self, context_or_page) -> None:
        """Injects stealth scripts to evade bot / automated script detection."""
        stealth_js = """
        // Mask navigator.webdriver
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });

        // Mock window.chrome runtime
        if (!window.chrome) {
            window.chrome = {};
        }
        window.chrome.runtime = window.chrome.runtime || {
            OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install' },
            PlatformArch: { X86_64: 'x86-64' },
            PlatformOs: { WIN: 'win' }
        };

        // Mock plugins to prevent zero-plugin automated browser detection
        if (!navigator.plugins || navigator.plugins.length === 0) {
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbhegnghamebmpefzkmmgfanflcou' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin' }
                ]
            });
        }

        // Mock languages
        if (!navigator.languages || navigator.languages.length === 0) {
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
        }
        """
        try:
            if hasattr(context_or_page, "add_init_script"):
                context_or_page.add_init_script(stealth_js)
        except Exception as e:
            logger.debug(f"Could not apply stealth script: {e}")

    def launch(self) -> Page:
        """
        Launches Chromium with persistent user profile or connects to real Chrome via CDP.
        Returns the active Page instance.
        """
        self.cfg.ensure_directories()
        profile_dir = self.cfg.browser_profile_dir

        # If already healthy, reuse page
        if self.is_healthy():
            logger.info("Reusing existing healthy browser context.")
            return self.page

        # 1. Attempt CDP connection if configured or port 9222 is active
        use_cdp = getattr(self.cfg, "use_cdp", False)
        cdp_url = getattr(self.cfg, "cdp_url", "http://localhost:9222")
        if use_cdp:
            try:
                logger.info(f"Connecting to real Chrome instance via CDP at {cdp_url}...")
                self.playwright = sync_playwright().start()
                browser = self.playwright.chromium.connect_over_cdp(cdp_url)
                contexts = browser.contexts
                self.context = contexts[0] if contexts else browser.new_context()
                pages = self.context.pages
                self.page = pages[0] if pages else self.context.new_page()
                self._apply_stealth(self.context)
                self.page.set_default_timeout(self.cfg.element_wait_timeout_s * 1000)
                logger.info("Successfully connected to real Chrome via CDP!")
                return self.page
            except Exception as cdp_err:
                logger.warning(f"Could not connect via CDP ({cdp_err}). Falling back to persistent context.")

        args = [
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
            "--no-default-browser-check",
            "--ignore-gpu-blocklist",
            "--enable-gpu-rasterization",
            "--enable-zero-copy",
            "--disable-infobars",
        ]

        # Ignore Playwright default that forces CPU software rendering (SwiftShader)
        ignore_default_args = [
            "--enable-unsafe-swiftshader",
        ]

        for attempt in range(1, 4):
            # Clean up dead handles and orphaned processes first
            self.close()
            self.kill_stale_chrome_processes()
            self.clean_stale_lockfile()

            logger.info(f"Launching persistent browser context from {profile_dir} (headless={self.cfg.headless}, attempt={attempt})")
            self.playwright = sync_playwright().start()

            try:
                # In visible mode, no_viewport=True allows --start-maximized to occupy the full native display
                viewport_setting = None if not self.cfg.headless else {"width": self.cfg.viewport_width, "height": self.cfg.viewport_height}
                self.context = self.playwright.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir),
                    headless=self.cfg.headless,
                    viewport=viewport_setting,
                    no_viewport=not self.cfg.headless,
                    args=args,
                    ignore_default_args=ignore_default_args,
                    timeout=self.cfg.page_load_timeout_s * 1000,
                )

                # Inject stealth anti-detection script
                self._apply_stealth(self.context)

                pages = self.context.pages
                if pages:
                    self.page = pages[0]
                else:
                    self.page = self.context.new_page()

                self.page.set_default_timeout(self.cfg.element_wait_timeout_s * 1000)
                return self.page
            except Exception as e:
                err_msg = str(e)
                if ("Opening in existing browser session" in err_msg or "profile is already in use" in err_msg) and attempt < 3:
                    logger.warning(f"Browser profile locked on attempt {attempt}. Forcing stale process cleanup and retrying...")
                    self.close()
                    time.sleep(2)
                else:
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

        self.kill_stale_chrome_processes()
        self.clean_stale_lockfile()

browser_manager = BrowserManager()
