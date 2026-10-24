"""
Schema validation for ExamForge bilingual question banks.
Uses both JSON Schema (draft-07) and Pydantic models for rigorous verification.
"""
from pathlib import Path
import json
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field, field_validator
import jsonschema
from core.config import config
from core.logging_config import logger

class OptionModel(BaseModel):
    id: str = Field(..., min_length=1)
    text: str

class LanguageContent(BaseModel):
    text: str = Field(..., min_length=1)
    options: List[OptionModel] = Field(..., min_length=2)

class ExplanationModel(BaseModel):
    en: str = Field(default="")
    hi: str = Field(default="")

class MCQQuestionModel(BaseModel):
    type: str = Field(default="MCQ")
    en: LanguageContent
    hi: LanguageContent
    correctOptionId: str = Field(..., min_length=1)
    subject: str = Field(..., min_length=1)
    topic: str = Field(..., min_length=1)
    has_image: bool = Field(default=False)
    explanation: ExplanationModel

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v != "MCQ":
            raise ValueError(f"Type must be 'MCQ', got '{v}'")
        return v

def load_canonical_schema(schema_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load JSON Schema definition from disk."""
    path = schema_path or config.default_schema_path
    if not path.exists():
        raise FileNotFoundError(f"Schema file not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def validate_json_schema(data: Any, schema_path: Optional[Path] = None) -> Tuple[bool, List[str]]:
    """
    Validates data against canonical JSON Schema.
    Returns:
        (is_valid, list_of_error_strings)
    """
    errors: List[str] = []
    try:
        schema = load_canonical_schema(schema_path)
    except Exception as e:
        return False, [f"Failed to load schema: {e}"]

    validator = jsonschema.Draft7Validator(schema)
    for error in validator.iter_errors(data):
        path = " -> ".join([str(p) for p in error.path]) if error.path else "root"
        errors.append(f"[{path}] {error.message}")

    return len(errors) == 0, errors

def validate_with_pydantic(data: Any) -> Tuple[bool, List[str], List[MCQQuestionModel]]:
    """
    Validates array of question items with Pydantic.
    Returns:
        (is_valid, list_of_errors, list_of_parsed_models)
    """
    errors: List[str] = []
    validated_models: List[MCQQuestionModel] = []

    if not isinstance(data, list):
        return False, ["Root structure must be a JSON array of questions"], []

    for idx, item in enumerate(data):
        try:
            model = MCQQuestionModel.model_validate(item)
            validated_models.append(model)
        except Exception as e:
            errors.append(f"Question index {idx}: {e}")

    return len(errors) == 0, errors, validated_models
