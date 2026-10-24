"""
Completeness and semantic alignment checks for ExamForge questions.
Validates option alignment across languages, answer ID integrity, and question counts.
"""
from typing import List, Dict, Any, Optional, Tuple

def check_question_completeness(
    questions: List[Dict[str, Any]],
    expected_count: Optional[int] = None
) -> Tuple[bool, List[str]]:
    """
    Validates structural completeness and alignment for a list of question dicts.
    Returns:
        (is_complete, issues_list)
    """
    issues: List[str] = []

    if not isinstance(questions, list):
        return False, ["Input must be a list of questions"]

    actual_count = len(questions)
    if expected_count is not None and expected_count > 0:
        if actual_count != expected_count:
            issues.append(
                f"Question count mismatch: expected {expected_count}, but extracted {actual_count}"
            )

    seen_en_texts = set()
    for idx, q in enumerate(questions):
        prefix = f"Question #{idx + 1}"
        
        # Check type
        q_type = q.get("type")
        if q_type != "MCQ":
            issues.append(f"{prefix}: Unsupported question type '{q_type}'")

        en = q.get("en", {})
        hi = q.get("hi", {})

        en_text = (en.get("text") or "").strip()
        hi_text = (hi.get("text") or "").strip()

        if not en_text:
            issues.append(f"{prefix}: English question text is empty")
        if not hi_text:
            issues.append(f"{prefix}: Hindi question text is empty")

        # Duplicate question detection
        if en_text:
            normalized_text = en_text.lower()
            if normalized_text in seen_en_texts:
                issues.append(f"{prefix}: Possible duplicate question (matches earlier English text)")
            seen_en_texts.add(normalized_text)

        # Options check
        en_opts = en.get("options", [])
        hi_opts = hi.get("options", [])

        if len(en_opts) < 2:
            issues.append(f"{prefix}: English options count is {len(en_opts)} (minimum 2 required)")
        if len(hi_opts) < 2:
            issues.append(f"{prefix}: Hindi options count is {len(hi_opts)} (minimum 2 required)")

        en_opt_ids = [opt.get("id") for opt in en_opts if isinstance(opt, dict)]
        hi_opt_ids = [opt.get("id") for opt in hi_opts if isinstance(opt, dict)]

        # Unique option IDs within language
        if len(en_opt_ids) != len(set(en_opt_ids)):
            issues.append(f"{prefix}: English options contain duplicate IDs: {en_opt_ids}")
        if len(hi_opt_ids) != len(set(hi_opt_ids)):
            issues.append(f"{prefix}: Hindi options contain duplicate IDs: {hi_opt_ids}")

        # Cross-language alignment
        if en_opt_ids != hi_opt_ids:
            issues.append(
                f"{prefix}: Option ID mismatch between languages: English {en_opt_ids} vs Hindi {hi_opt_ids}"
            )

        # Correct option ID verification
        correct_id = q.get("correctOptionId")
        if not correct_id:
            issues.append(f"{prefix}: Missing 'correctOptionId'")
        elif correct_id not in en_opt_ids:
            issues.append(
                f"{prefix}: 'correctOptionId' ('{correct_id}') is not in option IDs {en_opt_ids}"
            )

    return len(issues) == 0, issues
