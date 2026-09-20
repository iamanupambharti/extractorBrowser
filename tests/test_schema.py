"""
Unit tests for schema validation (JSON Schema and Pydantic).
"""
import copy
from validation.validate_json import validate_json_schema, validate_with_pydantic

def test_valid_question_schema(sample_valid_question):
    data = [sample_valid_question]
    ok, errors = validate_json_schema(data)
    assert ok, f"Expected valid schema, got errors: {errors}"
    assert len(errors) == 0

    p_ok, p_errors, models = validate_with_pydantic(data)
    assert p_ok, f"Expected valid pydantic model, got: {p_errors}"
    assert len(models) == 1

def test_missing_required_field(sample_valid_question):
    bad = copy.deepcopy(sample_valid_question)
    del bad["correctOptionId"]
    ok, errors = validate_json_schema([bad])
    assert not ok
    assert any("correctOptionId" in e for e in errors)

def test_invalid_type_enum(sample_valid_question):
    bad = copy.deepcopy(sample_valid_question)
    bad["type"] = "TRUE_FALSE"
    ok, errors = validate_json_schema([bad])
    assert not ok

    p_ok, p_errors, _ = validate_with_pydantic([bad])
    assert not p_ok

def test_empty_options_rejected(sample_valid_question):
    bad = copy.deepcopy(sample_valid_question)
    bad["en"]["options"] = []
    ok, errors = validate_json_schema([bad])
    assert not ok
