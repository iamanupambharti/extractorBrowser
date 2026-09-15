"""
Centralized selector registry for Gemini Web interface.
Organized in priority order: Accessible role/name > Stable aria-label > Scoped CSS.
"""
from typing import List

# Sign-in detection selectors (if these appear, manual login is needed)
AUTH_INDICATORS: List[str] = [
    "a[href*='accounts.google.com/signin']",
    "a:has-text('Sign in')",
    "button:has-text('Sign in')",
    "text='Sign in to Gemini'",
    "text='Sign in with Google'",
]

# Prompt composer input element locators
COMPOSER_SELECTORS: List[str] = [
    "div[role='textbox'][contenteditable='true']",
    "rich-textarea div[contenteditable='true']",
    "div[aria-label*='Ask Gemini']",
    "div[aria-label*='Enter a prompt']",
    "textarea[aria-label*='Ask Gemini']",
    ".ql-editor",
    "textarea",
]

# Send / Submit button locators
SEND_BUTTON_SELECTORS: List[str] = [
    "button[aria-label*='Send message']",
    "button[aria-label*='Send prompt']",
    "button[aria-label='Send']",
    "button.send-button",
    "button:has-text('Send')",
    "mat-icon:has-text('send')",
]

# Upload / Attachment trigger locators
UPLOAD_BUTTON_SELECTORS: List[str] = [
    "input[type='file']",
    "button[aria-label*='Upload file']",
    "button[aria-label*='Add files']",
    "button[aria-label*='Attach']",
    "button:has-text('Upload')",
    "button:has-text('Add files')",
]

# Uploaded attachment chip / indicator locators
ATTACHMENT_CHIP_SELECTORS: List[str] = [
    ".attachment-container",
    ".file-preview",
    "[data-test-id='attachment-chip']",
    "mat-chip",
    "div[aria-label*='.pdf']",
    "div:has-text('.pdf')",
]

# Generation in-progress / Stop button locators
STOP_GENERATION_SELECTORS: List[str] = [
    "button[aria-label*='Stop generating']",
    "button[aria-label*='Stop response']",
    "button:has-text('Stop generating')",
    "button:has-text('Stop')",
    "[aria-label*='Stop']",
]

# Assistant response message containers
RESPONSE_CONTAINER_SELECTORS: List[str] = [
    "model-response",
    "message-content",
    ".model-response-text",
    ".response-container",
    "[data-test-id='model-response-text']",
    "div.presented-content",
]

# Usage limit / Quota warning locators
USAGE_LIMIT_SELECTORS: List[str] = [
    "text='You've reached your limit'",
    "text='usage limit'",
    "text='rate limit'",
    "text='try again later'",
    "text='You have reached the message limit'",
]
