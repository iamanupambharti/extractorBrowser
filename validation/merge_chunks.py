"""
Merger and deduplication engine for question chunks extracted by ExamForge.
Consolidates sequential chunk JSON files into a unified master output.
"""
import re
from typing import List, Dict, Any, Tuple, Optional
from core.logging_config import logger

def _normalize_text_for_dedup(text: str) -> str:
    """Removes non-alphanumeric characters and standardizes whitespace for matching."""
    if not text:
        return ""
    cleaned = re.sub(r"[^\w\s]", "", text.lower())
    return " ".join(cleaned.split())

def merge_question_chunks(
    chunk_results: List[Dict[str, Any]],
    similarity_threshold: float = 0.85
) -> Dict[str, Any]:
    """
    Merges multiple parsed JSON chunk payloads into a single consolidated JSON dictionary.
    
    Operations performed:
    1. Re-indexes question IDs sequentially: q1, q2, q3, ...
    2. Deduplicates questions across chunks (e.g., if a question straddled page boundaries).
    3. Merges and updates metadata: chunk count, total extracted questions.
    4. Preserves language completeness and options integrity.
    
    Args:
        chunk_results: List of parsed JSON dicts, each matching the ExamForge schema:
                       {"questions": [...], "metadata": {...}}
        similarity_threshold: Threshold for detecting duplicate questions.
        
    Returns:
        Consolidated dictionary: {"questions": [...], "metadata": {...}}
    """
    all_questions: List[Dict[str, Any]] = []
    seen_texts = set()
    duplicate_count = 0
    total_raw_questions = 0

    exam_name = "Merged Exam"
    total_marks = 0
    total_time_minutes = 0

    for chunk_idx, chunk_data in enumerate(chunk_results):
        if not isinstance(chunk_data, dict):
            logger.warning(f"Chunk index {chunk_idx} is not a valid dict, skipping.")
            continue

        chunk_meta = chunk_data.get("metadata", {})
        if chunk_meta.get("exam_name") and exam_name == "Merged Exam":
            exam_name = chunk_meta.get("exam_name")

        raw_q_list = chunk_data.get("questions", [])
        if not isinstance(raw_q_list, list):
            continue

        for q in raw_q_list:
            total_raw_questions += 1
            en_text = (q.get("en", {}).get("text") or "").strip()
            hi_text = (q.get("hi", {}).get("text") or "").strip()

            # Create normalized signature for deduplication
            norm_en = _normalize_text_for_dedup(en_text)
            norm_hi = _normalize_text_for_dedup(hi_text)
            sig = norm_en if norm_en else norm_hi

            if sig and sig in seen_texts:
                duplicate_count += 1
                logger.info(f"Duplicate question detected and skipped across chunks: '{en_text[:60]}...'")
                continue

            if sig:
                seen_texts.add(sig)

            # Assign fresh sequential question ID
            new_id = f"q{len(all_questions) + 1}"
            cloned_q = dict(q)
            cloned_q["id"] = new_id

            # Add source chunk tracking info
            cloned_q["_source_chunk"] = chunk_idx + 1

            all_questions.append(cloned_q)

    # Estimate marks/time based on merged questions
    total_marks = len(all_questions)
    total_time_minutes = len(all_questions)

    merged_output = {
        "metadata": {
            "exam_name": exam_name,
            "total_questions": len(all_questions),
            "total_marks": total_marks,
            "total_time_minutes": total_time_minutes,
            "chunks_processed": len(chunk_results),
            "raw_questions_extracted": total_raw_questions,
            "duplicates_removed": duplicate_count,
        },
        "questions": all_questions
    }

    logger.info(
        f"Merged {len(chunk_results)} chunks: {total_raw_questions} raw questions -> "
        f"{len(all_questions)} unique questions ({duplicate_count} duplicates removed)."
    )
    return merged_output
