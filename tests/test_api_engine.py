"""
Unit tests for the Gemini API Engine and configuration.
Verifies API key resolution, error handling, structured payload generation, and mock execution.
"""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from core.config import AppConfig
from core.gemini_api_engine import GeminiAPIEngine

def test_api_key_resolution_missing():
    """Ensures missing API key raises informative ValueError."""
    cfg = AppConfig()
    cfg.gemini_api_key = ""
    engine = GeminiAPIEngine(app_config=cfg)

    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="Gemini API Key is not set"):
            engine.get_api_key()

def test_api_key_resolution_from_param_or_config():
    """Ensures API key resolves properly from config or explicit parameter."""
    cfg = AppConfig()
    cfg.gemini_api_key = "config_key_123"
    engine = GeminiAPIEngine(app_config=cfg)

    assert engine.get_api_key() == "config_key_123"
    assert engine.get_api_key("custom_param_key") == "custom_param_key"

def test_extract_from_pdf_nonexistent(tmp_path):
    """Ensures missing PDF file raises FileNotFoundError."""
    cfg = AppConfig()
    cfg.gemini_api_key = "test_key"
    engine = GeminiAPIEngine(app_config=cfg)

    fake_path = tmp_path / "does_not_exist.pdf"
    with pytest.raises(FileNotFoundError):
        engine.extract_from_pdf(fake_path, "Extract questions")

def test_extract_from_pdf_mocked(tmp_path):
    """Tests mocked API generation returns raw text properly."""
    cfg = AppConfig()
    cfg.gemini_api_key = "test_key"
    engine = GeminiAPIEngine(app_config=cfg)

    # Create dummy pdf
    pdf_file = tmp_path / "sample.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 test dummy content")

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '[{"type": "MCQ", "en": {"text": "What is 2+2?", "options": [{"id": "opt1", "text": "4"}, {"id": "opt2", "text": "5"}]}, "hi": {"text": "2+2 क्या है?", "options": [{"id": "opt1", "text": "4"}, {"id": "opt2", "text": "5"}]}, "correctOptionId": "opt1", "subject": "Math", "topic": "Arithmetic", "has_image": false, "explanation": {"en": "2+2=4", "hi": "2+2=4"}}]'
    mock_client.models.generate_content.return_value = mock_response

    with patch.object(engine, "get_client", return_value=mock_client):
        raw_text = engine.extract_from_pdf(pdf_file, "Extract questions")
        assert "What is 2+2?" in raw_text
        assert mock_client.models.generate_content.called
