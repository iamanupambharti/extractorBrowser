"""
Helper script to launch genuine installed Google Chrome with remote debugging on port 9222.
This bypasses all bot detection, 'running on a script' warnings, and Cloudflare challenges,
because it runs the authentic signed Chrome executable without automation flags.
"""
import os
import subprocess
import sys
from pathlib import Path
from core.config import config

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

def find_browser_executable() -> Path:
    for p in CHROME_PATHS:
        candidate = Path(p)
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not find installed Google Chrome or Microsoft Edge executable.")

def launch_real_chrome(target_url: str = None) -> subprocess.Popen:
    browser_exe = find_browser_executable()
    url = target_url or config.target_url
    debug_dir = config.chrome_debug_dir
    debug_dir.mkdir(parents=True, exist_ok=True)

    print("=================================================================")
    print(" ExamForge Browser — Real Chrome Stealth Launcher (CDP Mode)")
    print(f" Executable: {browser_exe}")
    print(f" Debug Port: 9222")
    print(f" Profile Directory: {debug_dir}")
    print(f" Target URL: {url}")
    print("=================================================================")
    print("\n👉 Genuine browser is launching without automation flags.")
    print("👉 Websites will NOT detect automated scripts or Playwright.")
    print("👉 ExamForge can now connect seamlessly via CDP on port 9222.\n")

    cmd = [
        str(browser_exe),
        "--remote-debugging-port=9222",
        f"--user-data-dir={debug_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--start-maximized",
        url,
    ]

    proc = subprocess.Popen(cmd)
    return proc

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    proc = launch_real_chrome(target)
    print("Press Enter to exit launcher (browser will stay open)...")
    try:
        input()
    except (KeyboardInterrupt, EOFError):
        pass
