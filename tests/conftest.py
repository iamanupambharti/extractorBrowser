"""
Pytest configuration and shared test fixtures for ExamForge Browser.
"""
import pytest
from pathlib import Path
import json

@pytest.fixture
def sample_valid_question():
    return {
        "type": "MCQ",
        "en": {
            "text": "What is the capital of France?",
            "options": [
                {"id": "opt1", "text": "Berlin"},
                {"id": "opt2", "text": "Madrid"},
                {"id": "opt3", "text": "Paris"},
                {"id": "opt4", "text": "Rome"}
            ]
        },
        "hi": {
            "text": "फ्रांस की राजधानी क्या है?",
            "options": [
                {"id": "opt1", "text": "बर्लिन"},
                {"id": "opt2", "text": "मैड्रिड"},
                {"id": "opt3", "text": "पेरिस"},
                {"id": "opt4", "text": "रोम"}
            ]
        },
        "correctOptionId": "opt3",
        "subject": "Geography",
        "topic": "European Capitals",
        "has_image": False,
        "explanation": {
            "en": "Paris is the capital and most populous city of France.",
            "hi": "पेरिस फ्रांस की राजधानी और सबसे बड़ा शहर है।"
        }
    }

@pytest.fixture
def sample_raw_fenced_response(sample_valid_question):
    payload = [sample_valid_question]
    return f"""Here is the extracted question data:

```json
{json.dumps(payload, indent=2)}
```

Hope this helps!"""

@pytest.fixture
def sample_raw_unfenced_response(sample_valid_question):
    payload = [sample_valid_question]
    return json.dumps(payload, indent=2)
