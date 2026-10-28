"""
Direct Google Gemini API execution engine for ExamForge.
Uses official google-genai SDK to provide high-speed, 100% reliable PDF extraction
without browser automation, bot detection, or UI selector breakage.
"""
from pathlib import Path
import os
import time
from typing import Optional, Tuple
from google import genai
from google.genai import types

from core.config import config
from core.logging_config import logger

class GeminiAPIEngine:
    """Handles direct multimodal PDF extraction via the official Google GenAI API."""

    def __init__(self, app_config=config):
        self.cfg = app_config

    def get_api_key(self, custom_key: Optional[str] = None) -> str:
        """Resolves the Gemini API key from parameters, config, or environment."""
        key = (custom_key or self.cfg.gemini_api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        if not key:
            raise ValueError(
                "Gemini API Key is not set. Please enter your Gemini API Key in the "
                "Streamlit Dashboard settings or set GEMINI_API_KEY in your .env file."
            )
        return key

    def get_client(self, custom_key: Optional[str] = None) -> genai.Client:
        """Instantiates the Google GenAI client with resolved API key."""
        api_key = self.get_api_key(custom_key)
        return genai.Client(api_key=api_key)

    def test_connection(self, custom_key: Optional[str] = None) -> Tuple[bool, str]:
        """
        Tests API key validity and connectivity.
        Returns:
            (is_successful, message)
        """
        try:
            client = self.get_client(custom_key)
            model_name = getattr(self.cfg, "gemini_model", "gemini-2.5-flash")
            
            # Simple test prompt
            response = client.models.generate_content(
                model=model_name,
                contents="Reply with 'OK'",
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=10,
                )
            )
            if response and response.text:
                return True, f"API connected successfully! Model '{model_name}' is responsive."
            return False, "Received empty response from Gemini API."
        except Exception as e:
            err_msg = str(e)
            logger.error(f"Gemini API connection test failed: {err_msg}")
            # Try fallback to gemini-1.5-flash if 2.5-flash is not available for this key
            if "2.5-flash" in str(getattr(self.cfg, "gemini_model", "")) and ("not found" in err_msg.lower() or "not supported" in err_msg.lower()):
                try:
                    logger.info("Attempting fallback to gemini-1.5-flash...")
                    fallback_client = self.get_client(custom_key)
                    resp = fallback_client.models.generate_content(
                        model="gemini-1.5-flash",
                        contents="Reply with 'OK'",
                        config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=10)
                    )
                    if resp and resp.text:
                        self.cfg.gemini_model = "gemini-1.5-flash"
                        return True, "Connected successfully using gemini-1.5-flash fallback!"
                except Exception as fb_err:
                    err_msg = str(fb_err)
            return False, f"API Connection Error: {err_msg}"

    def extract_from_pdf(
        self,
        pdf_path: Path,
        prompt_text: str,
        custom_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> str:
        """
        Submits PDF and extraction prompt directly to the Gemini API.
        
        Args:
            pdf_path: Path to examination PDF.
            prompt_text: Prompt text defining extraction directives and format.
            custom_key: Optional API key override.
            model_name: Optional model override (default: from config).
            
        Returns:
            Raw generated JSON string from the model.
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file does not exist: {pdf_path}")

        client = self.get_client(custom_key)
        target_model = model_name or getattr(self.cfg, "gemini_model", "gemini-2.5-flash")
        
        file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
        logger.info(f"Preparing Gemini API extraction for '{pdf_path.name}' ({file_size_mb:.2f} MB) using model '{target_model}'")

        uploaded_file_ref = None
        try:
            # If under 20MB, pass inline bytes directly for zero-upload latency
            if file_size_mb <= 20.0:
                logger.info("Passing PDF data inline as application/pdf part.")
                with open(pdf_path, "rb") as f:
                    pdf_bytes = f.read()
                pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
                contents = [pdf_part, prompt_text]
            else:
                # Upload using Google GenAI Files API for larger documents
                logger.info("Uploading PDF via GenAI Files API (>20MB)...")
                uploaded_file_ref = client.files.upload(file=str(pdf_path))
                # Wait for file processing if needed
                start_wait = time.time()
                while uploaded_file_ref.state.name == "PROCESSING":
                    if time.time() - start_wait > 60:
                        raise TimeoutError("File processing timed out on Gemini Files API.")
                    time.sleep(2)
                    uploaded_file_ref = client.files.get(name=uploaded_file_ref.name)
                contents = [uploaded_file_ref, prompt_text]

            # Request structured JSON output directly
            gen_config = types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,  # Low temperature for strict factual extraction
            )

            logger.info(f"Submitting extraction request to Gemini API ({target_model})...")
            start_gen = time.time()
            
            try:
                response = client.models.generate_content(
                    model=target_model,
                    contents=contents,
                    config=gen_config,
                )
            except Exception as call_err:
                # Automatic fallback if model 2.5-flash isn't available
                if target_model != "gemini-1.5-flash" and ("not found" in str(call_err).lower() or "404" in str(call_err)):
                    logger.warning(f"Model '{target_model}' encountered error; falling back to 'gemini-1.5-flash': {call_err}")
                    target_model = "gemini-1.5-flash"
                    self.cfg.gemini_model = target_model
                    response = client.models.generate_content(
                        model=target_model,
                        contents=contents,
                        config=gen_config,
                    )
                else:
                    raise

            duration = time.time() - start_gen
            raw_text = response.text or ""
            logger.info(f"Gemini API returned {len(raw_text)} chars in {duration:.1f}s.")

            if not raw_text.strip():
                raise RuntimeError("Gemini API returned empty response text.")

            return raw_text

        finally:
            # Clean up uploaded remote file if used
            if uploaded_file_ref:
                try:
                    client.files.delete(name=uploaded_file_ref.name)
                    logger.debug("Deleted temporary remote file from Files API.")
                except Exception as del_err:
                    logger.debug(f"Could not delete remote file ref: {del_err}")

gemini_api_engine = GeminiAPIEngine()
