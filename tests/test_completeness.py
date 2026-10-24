"""
Unit tests for question completeness, option ID alignment, and quality flags.
"""
import copy
from validation.completeness import check_question_completeness
from validation.quality_flags import audit_question_quality, generate_validation_report

def test_complete_valid_question(sample_valid_question):
    ok, issues = check_question_completeness([sample_valid_question], expected_count=1)
    assert ok
    assert len(issues) == 0

def test_count_mismatch_reported(sample_valid_question):
    ok, issues = check_question_completeness([sample_valid_question], expected_count=5)
    assert not ok
    assert any("expected 5, but extracted 1" in issue for issue in issues)

def test_option_id_mismatch_between_languages(sample_valid_question):
    bad = copy.deepcopy(sample_valid_question)
    bad["hi"]["options"][0]["id"] = "opt99"
    ok, issues = check_question_completeness([bad])
    assert not ok
    assert any("Option ID mismatch between languages" in issue for issue in issues)

def test_correct_option_id_not_in_options(sample_valid_question):
    bad = copy.deepcopy(sample_valid_question)
    bad["correctOptionId"] = "opt999"
    ok, issues = check_question_completeness([bad])
    assert not ok
    assert any("not in option IDs" in issue for issue in issues)

def test_quality_flags_audit(sample_valid_question):
    bad = copy.deepcopy(sample_valid_question)
    bad["en"]["text"] = "Short"  # < 10 chars
    bad["explanation"]["hi"] = "" # missing hindi explanation
    warnings = audit_question_quality([bad])
    assert len(warnings) >= 2
    types = [w["type"] for w in warnings]
    assert "SHORT_TEXT" in types
    assert "MISSING_EXPLANATION" in types

def test_validation_report_generation(sample_valid_question):
    report = generate_validation_report(
        job_id="test_job",
        schema_valid=True,
        errors=[],
        warnings=[{"question_index": 1, "type": "INFO", "message": "Check needed"}],
        extracted_count=1,
        expected_count=1,
    )
    assert report["schema_valid"] is True
    assert report["content_review_required"] is True
    assert report["extracted_question_count"] == 1
