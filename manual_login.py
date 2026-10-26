"""
Simple launcher script to open the dedicated browser profile for manual login.
Run this to log in to ChatGPT or Google Gemini without automated timeouts closing the window.
"""
from pathlib import Path
import time
from playwright.sync_api import sync_playwright

from core.config import config
from browser.launch import browser_manager

def launch_manual_login():
    print("=======================================================")
    print(" ExamForge Browser — Manual Authentication Mode")
    print(f" Profile Directory: {config.browser_profile_dir}")
    print(f" Opening URL: {config.target_url}")
    print("=======================================================")
    print("\n👉 A native Chromium browser window is opening.")
    print("👉 Please log in to your ChatGPT or Google account.")
    print("👉 Once you are logged in and see the chat screen,")
    print("   simply close the browser window or press Ctrl+C in this terminal.")
    print("👉 Your login session and cookies will be automatically saved!\n")

    browser_manager.kill_stale_chrome_processes()
    browser_manager.clean_stale_lockfile()

    playwright = sync_playwright().start()
    args = [
        "--disable-blink-features=AutomationControlled",
        "--start-maximized",
        "--no-default-browser-check",
    ]

    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(config.browser_profile_dir),
        headless=False,
        no_viewport=True,
        args=args,
    )

    page = context.pages[0] if context.pages else context.new_page()
    page.goto(config.target_url)

    try:
        # Keep window open until user closes it
        while len(context.pages) > 0:
            time.sleep(1)
    except Exception:
        pass
    finally:
        try:
            context.close()
            playwright.stop()
        except Exception:
            pass
        print("\n✅ Session saved successfully to browser profile!")

if __name__ == "__main__":
    launch_manual_login()
