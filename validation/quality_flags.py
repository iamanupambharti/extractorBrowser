"""
Quality auditing and pedagogical flag generator for extracted questions.
Does not claim factual infallibility; highlights areas requiring human review.
"""
from typing import List, Dict, Any, Optional
import re
from core.config import config

IMAGE_KEYWORDS = [
    "figure", "fig.", "diagram", "graph", "circuit", "chart", "map", "table",
    "चित्र", "आरेख", "ग्राफ", "मानचित्र", "तालिका"
]

def check_math_delimiters(text: str) -> bool:
    """Checks if LaTeX dollar signs are balanced."""
    dollar_count = text.count("$")
    return (dollar_count % 2) == 0

def audit_question_quality(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Audits question items and returns a list of warnings with question indices.
    """
    warnings: List[Dict[str, Any]] = []

    for idx, q in enumerate(questions):
        q_num = idx + 1
        en = q.get("en", {})
        hi = q.get("hi", {})
        en_text = (en.get("text") or "").strip()
        hi_text = (hi.get("text") or "").strip()
        has_image = q.get("has_image", False)
        explanation = q.get("explanation", {})

        # Suspiciously short text
        if len(en_text) < 10:
            warnings.append({
                "question_index": q_num,
                "type": "SHORT_TEXT",
                "message": f"Question {q_num}: English text is suspiciously short ({len(en_text)} chars)."
            })
        if len(hi_text) < 10:
            warnings.append({
                "question_index": q_num,
                "type": "SHORT_TEXT",
                "message": f"Question {q_num}: Hindi text is suspiciously short ({len(hi_text)} chars)."
            })

        # Math delimiters
        if not check_math_delimiters(en_text) or not check_math_delimiters(hi_text):
            warnings.append({
                "question_index": q_num,
                "type": "UNBALANCED_MATH",
                "message": f"Question {q_num}: Unbalanced '$' LaTeX delimiters detected in question text."
            })

        # Missing explanation
        exp_en = (explanation.get("en") or "").strip()
        exp_hi = (explanation.get("hi") or "").strip()
        if not exp_en:
            warnings.append({
                "question_index": q_num,
                "type": "MISSING_EXPLANATION",
                "message": f"Question {q_num}: English explanation is missing or blank."
            })
        if not exp_hi:
            warnings.append({
                "question_index": q_num,
                "type": "MISSING_EXPLANATION",
                "message": f"Question {q_num}: Hindi explanation is missing or blank."
            })

        # Image reference without has_image flag
        combined_text = f"{en_text} {hi_text}".lower()
        if not has_image:
            for kw in IMAGE_KEYWORDS:
                if re.search(r"\b" + re.escape(kw) + r"\b", combined_text):
                    warnings.append({
                        "question_index": q_num,
                        "type": "POSSIBLE_UNMARKED_IMAGE",
                        "message": f"Question {q_num}: Text mentions '{kw}' but 'has_image' is false."
                    })
                    break

        # Empty options text
        for opt in en.get("options", []):
            if not (opt.get("text") or "").strip():
                warnings.append({
                    "question_index": q_num,
                    "type": "EMPTY_OPTION",
                    "message": f"Question {q_num}: English option '{opt.get('id')}' text is empty."
                })
        for opt in hi.get("options", []):
            if not (opt.get("text") or "").strip():
                warnings.append({
                    "question_index": q_num,
                    "type": "EMPTY_OPTION",
                    "message": f"Question {q_num}: Hindi option '{opt.get('id')}' text is empty."
                })

    return warnings

def generate_validation_report(
    job_id: str,
    schema_valid: bool,
    errors: List[str],
    warnings: List[Dict[str, Any]],
    extracted_count: int,
    expected_count: Optional[int] = None,
    prompt_version: str = config.prompt_version,
    schema_version: str = config.schema_version,
) -> Dict[str, Any]:
    """Generates the structured validation report conforming to Section 11.4."""
    content_review_required = (not schema_valid) or (len(warnings) > 0) or (
        expected_count is not None and expected_count != extracted_count
    )

    return {
        "job_id": job_id,
        "schema_valid": schema_valid,
        "content_review_required": content_review_required,
        "expected_question_count": expected_count,
        "extracted_question_count": extracted_count,
        "errors": errors,
        "warnings": [w["message"] if isinstance(w, dict) else str(w) for w in warnings],
        "detailed_warnings": warnings,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
    }
