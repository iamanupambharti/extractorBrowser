import pytest
from pathlib import Path
from core.pdf_splitter import split_pdf, PDFChunk
from validation.merge_chunks import merge_question_chunks
import fitz

def test_split_pdf_small(tmp_path):
    # Create a 2-page test PDF
    pdf_path = tmp_path / "test_small.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    doc.save(str(pdf_path))
    doc.close()

    out_dir = tmp_path / "chunks"
    chunks = split_pdf(pdf_path, out_dir, chunk_size=3, min_pages_to_split=2)
    
    # 2 pages <= 2 min_pages_to_split -> 1 single chunk
    assert len(chunks) == 1
    assert chunks[0].chunk_path == pdf_path
    assert chunks[0].total_chunks == 1
    assert chunks[0].page_count == 2

def test_split_pdf_multi_page(tmp_path):
    # Create a 7-page test PDF
    pdf_path = tmp_path / "test_multi.pdf"
    doc = fitz.open()
    for _ in range(7):
        doc.new_page()
    doc.save(str(pdf_path))
    doc.close()

    out_dir = tmp_path / "chunks"
    chunks = split_pdf(pdf_path, out_dir, chunk_size=3, min_pages_to_split=2)
    
    # 7 pages / 3 per chunk -> 3 chunks (3, 3, 1)
    assert len(chunks) == 3
    assert chunks[0].start_page == 1
    assert chunks[0].end_page == 3
    assert chunks[0].page_count == 3
    assert chunks[1].start_page == 4
    assert chunks[1].end_page == 6
    assert chunks[1].page_count == 3
    assert chunks[2].start_page == 7
    assert chunks[2].end_page == 7
    assert chunks[2].page_count == 1

    # Verify generated chunk PDFs actually exist and have correct page count
    for c in chunks:
        assert c.chunk_path.exists()
        c_doc = fitz.open(c.chunk_path)
        assert c_doc.page_count == c.page_count
        c_doc.close()

def test_merge_question_chunks():
    chunk1 = {
        "metadata": {"exam_name": "Physics Mock", "total_questions": 2},
        "questions": [
            {
                "id": "q1",
                "type": "MCQ",
                "en": {"text": "What is velocity?", "options": [{"id": "a", "text": "Speed with direction"}]},
                "hi": {"text": "वेग क्या है?", "options": [{"id": "a", "text": "दिशा के साथ गति"}]},
                "correct_option_id": "a"
            },
            {
                "id": "q2",
                "type": "MCQ",
                "en": {"text": "What is acceleration?", "options": [{"id": "a", "text": "Rate of change of velocity"}]},
                "hi": {"text": "त्वरण क्या है?", "options": [{"id": "a", "text": "वेग परिवर्तन की दर"}]},
                "correct_option_id": "a"
            }
        ]
    }
    chunk2 = {
        "metadata": {"exam_name": "Physics Mock", "total_questions": 2},
        "questions": [
            {
                # Duplicate of q2 (e.g. straddling chunk boundary)
                "id": "q1",
                "type": "MCQ",
                "en": {"text": "What is acceleration?", "options": [{"id": "a", "text": "Rate of change of velocity"}]},
                "hi": {"text": "त्वरण क्या है?", "options": [{"id": "a", "text": "वेग परिवर्तन की दर"}]},
                "correct_option_id": "a"
            },
            {
                "id": "q2",
                "type": "MCQ",
                "en": {"text": "What is force?", "options": [{"id": "a", "text": "Mass times acceleration"}]},
                "hi": {"text": "बल क्या है?", "options": [{"id": "a", "text": "द्रव्यमान गुणा त्वरण"}]},
                "correct_option_id": "a"
            }
        ]
    }

    merged = merge_question_chunks([chunk1, chunk2])
    questions = merged["questions"]
    
    # Total unique should be 3 (q2 duplicate skipped)
    assert len(questions) == 3
    assert questions[0]["id"] == "q1"
    assert questions[1]["id"] == "q2"
    assert questions[2]["id"] == "q3"

    assert questions[0]["en"]["text"] == "What is velocity?"
    assert questions[1]["en"]["text"] == "What is acceleration?"
    assert questions[2]["en"]["text"] == "What is force?"

    assert merged["metadata"]["duplicates_removed"] == 1
    assert merged["metadata"]["raw_questions_extracted"] == 4
