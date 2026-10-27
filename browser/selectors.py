"""
Centralized selector registry for Gemini Web interface.
Organized in priority order: Accessible role/name > Stable aria-label > Scoped CSS.
"""
from typing import List

# Sign-in detection selectors (if these appear, manual login is needed)
AUTH_INDICATORS: List[str] = [
    # Gemini
    "a[href*='accounts.google.com/signin']",
    "a:has-text('Sign in')",
    "button:has-text('Sign in')",
    "text='Sign in to Gemini'",
    "text='Sign in with Google'",
    # ChatGPT
    "button[data-testid='login-button']",
    "a[href*='/auth/login']",
    "button:has-text('Log in')",
    "button:has-text('Sign up')",
    "text='Welcome to ChatGPT'",
    "text='Log in with your OpenAI account'",
]

# Prompt composer input element locators
COMPOSER_SELECTORS: List[str] = [
    # ChatGPT
    "#prompt-textarea",
    "textarea#prompt-textarea",
    "div#prompt-textarea[contenteditable='true']",
    "div[id='prompt-textarea']",
    "textarea[placeholder*='Message ChatGPT']",
    "textarea[placeholder*='Ask anything']",
    "textarea[placeholder*='Message']",
    "form textarea",
    # Gemini
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
    # ChatGPT
    "button[data-testid='send-button']",
    "button[data-testid='fruitjuice-send-button']",
    "button[aria-label='Send prompt']",
    "button[aria-label='Send message']",
    "form button[type='submit']",
    # Gemini
    "button[aria-label*='Send message']",
    "button[aria-label*='Send prompt']",
    "button[aria-label='Send']",
    "button.send-button",
    "button:has-text('Send')",
    "mat-icon:has-text('send')",
]

# Upload / Attachment trigger locators
UPLOAD_BUTTON_SELECTORS: List[str] = [
    # ChatGPT
    "button[aria-label='Attach files']",
    "button[aria-label*='Attach']",
    "button[data-testid='attach-button']",
    "button[aria-label*='Upload']",
    # Gemini
    "button[aria-label*='Add files']",
    "button[aria-label*='Upload files']",
    "button[aria-label*='Upload file']",
    "button[aria-label*='Open upload file menu']",
    "button[aria-label*='Open file upload menu']",
    "button[aria-label*='Open upload menu']",
    "button[aria-label*='Add image or document']",
    "button[aria-label*='Add content']",
    "button[aria-label*='Add tools']",
    "button[aria-label*='Attach']",
    "button[aria-label*='Upload']",
    "button[aria-label*='Add']",
    "button[mattooltip*='Upload']",
    "button[mattooltip*='Add']",
    "button:has(mat-icon:has-text('add'))",
    "button:has(mat-icon:has-text('attach_file'))",
    "button:has(span:has-text('add'))",
    "button:has(span:has-text('attach_file'))",
    "button.upload-button",
    "button.file-upload-button",
    "button:has-text('Upload')",
    "button:has-text('Add files')",
    "button:has-text('Attach')",
    "[data-test-id*='upload']",
    "[data-test-id*='attach']",
    "button[aria-haspopup='menu']",
]

# Menu item locators when clicking '+' / upload button reveals a popup menu
UPLOAD_MENU_ITEM_SELECTORS: List[str] = [
    "[role='menuitem']:has-text('Upload from computer')",
    "[role='menuitem']:has-text('Upload files')",
    "[role='menuitem']:has-text('Upload file')",
    "[role='menuitem']:has-text('Upload')",
    "[role='menuitem']:has-text('computer')",
    "button:has-text('Upload from computer')",
    "button:has-text('Upload files')",
    "button:has-text('Upload')",
    "div[role='menuitem']:has-text('Upload from computer')",
    "div[role='menuitem']:has-text('Upload files')",
    "div[role='menuitem']:has-text('Upload')",
    "span:has-text('Upload from computer')",
    "span:has-text('Upload files')",
    "span:has-text('Upload')",
    "mat-menu-item:has-text('Upload')",
    "button[aria-label*='Upload from computer']",
    "button[aria-label*='Upload files']",
]

# Uploaded attachment chip / indicator locators
ATTACHMENT_CHIP_SELECTORS: List[str] = [
    ".attachment-container",
    ".file-preview",
    "[data-test-id='attachment-chip']",
    "mat-chip",
    "div.file-card",
    "div.attachment",
    "div.attachment-preview",
    "file-preview-card",
    "uploader-file-card",
    "div[class*='attachment']",
    "div[class*='chip']",
    "div[class*='preview']",
    "button[aria-label*='Remove file']",
    "button[aria-label*='Remove attachment']",
    "button[aria-label*='Delete file']",
    "button[aria-label*='Remove']",
    "div[aria-label*='.pdf']",
    "div:has-text('.pdf')",
    "span:has-text('.pdf')",
    "div:has-text('PDF')",
]

# Generation in-progress / Stop button locators (strict locators to prevent false matches on question text)
STOP_GENERATION_SELECTORS: List[str] = [
    "button[aria-label='Stop response']",
    "button[aria-label='Stop generating']",
    "button[aria-label*='Stop response']",
    "button[aria-label*='Stop generating']",
    "button[data-test-id='stop-button']",
    "button:has(mat-icon:has-text('stop'))",
]

# Response completed indicators (rendered after generation concludes)
RESPONSE_COMPLETED_SELECTORS: List[str] = [
    # ChatGPT
    "button[data-testid='copy-turn-action-button']",
    "button[aria-label='Copy']",
    "button[aria-label='Good response']",
    "button[aria-label='Bad response']",
    # Gemini
    "button[aria-label*='Copy']",
    "button[aria-label*='Copy response']",
    "button[aria-label*='Copy code']",
    "button[aria-label*='Good response']",
    "button[aria-label*='Modify response']",
    "button[aria-label*='Share & export']",
    "button[aria-label*='Share response']",
    "mat-icon:has-text('content_copy')",
    "mat-icon:has-text('thumb_up')",
    "[data-test-id*='copy']",
]

# Assistant response message containers
RESPONSE_CONTAINER_SELECTORS: List[str] = [
    # ChatGPT
    "div[data-message-author-role='assistant']",
    "div.agent-turn",
    "div.markdown",
    # Gemini
    "model-response",
    "message-content",
    ".model-response-text",
    ".response-container",
    "[data-test-id='model-response-text']",
    "div.presented-content",
    "pre code",
]

# Usage limit / Quota warning locators
USAGE_LIMIT_SELECTORS: List[str] = [
    "text='You've reached your limit'",
    "text='usage limit'",
    "text='rate limit'",
    "text='try again later'",
    "text='You have reached the message limit'",
]
