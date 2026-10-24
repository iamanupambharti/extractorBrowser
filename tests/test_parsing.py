"""
Unit tests for response parsing and markdown fence handling.
"""
from validation.parse_response import extract_json_text, parse_raw_response

def test_extract_json_from_clean_json(sample_raw_unfenced_response):
    extracted = extract_json_text(sample_raw_unfenced_response)
    assert extracted.startswith("[")
    assert extracted.endswith("]")

def test_extract_json_from_fenced_response(sample_raw_fenced_response):
    extracted = extract_json_text(sample_raw_fenced_response)
    assert not extracted.startswith("```")
    assert extracted.startswith("[")
    assert extracted.endswith("]")

def test_parse_valid_response(sample_raw_fenced_response):
    data, err = parse_raw_response(sample_raw_fenced_response)
    assert err is None
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["type"] == "MCQ"

def test_parse_empty_response():
    data, err = parse_raw_response("")
    assert data is None
    assert "Empty response" in err

def test_parse_invalid_json():
    invalid_raw = "```json\n[{\"type\": \"MCQ\", \"en\": {unclosed}\n```"
    data, err = parse_raw_response(invalid_raw)
    assert data is None
    assert "parse error" in err.lower()
