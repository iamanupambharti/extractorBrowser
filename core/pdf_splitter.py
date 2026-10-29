"""
PDF Splitting utility for ExamForge.
Splits large multi-page exam PDFs into smaller digestible chunks for Gemini.
"""
import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import fitz

from core.logging_config import logger

@dataclass
class PDFChunk:
    chunk_index: int          # 1-based index (e.g. 1, 2, 3)
    start_page: int           # 1-based inclusive start page
    end_page: int             # 1-based inclusive end page
    total_chunks: int         # Total number of chunks
    chunk_path: Path          # Path to the generated chunk PDF
    page_count: int           # Number of pages in this chunk


def split_pdf(
    input_path: Path,
    output_dir: Path,
    chunk_size: int = 3,
    min_pages_to_split: int = 2
) -> List[PDFChunk]:
    """
    Splits an input PDF into smaller chunks if page_count > min_pages_to_split.
    If page_count <= min_pages_to_split, returns a single chunk referencing the original file.
    
    Args:
        input_path: Path to the source PDF.
        output_dir: Directory where split PDF files will be stored.
        chunk_size: Maximum pages per chunk (default: 3).
        min_pages_to_split: Threshold of pages to trigger splitting (default: 2).
        
    Returns:
        List of PDFChunk objects in order.
    """
    input_path = Path(input_path).resolve()
    if not input_path.exists() or not input_path.is_file():
        raise FileNotFoundError(f"Source PDF does not exist: {input_path}")
    
    doc = fitz.open(input_path)
    total_pages = doc.page_count
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # If file doesn't need splitting, return 1 chunk referencing the source
    if total_pages <= min_pages_to_split:
        doc.close()
        return [
            PDFChunk(
                chunk_index=1,
                start_page=1,
                end_page=total_pages,
                total_chunks=1,
                chunk_path=input_path,
                page_count=total_pages
            )
        ]
    
    num_chunks = math.ceil(total_pages / chunk_size)
    chunks: List[PDFChunk] = []
    stem = input_path.stem
    
    logger.info(
        f"Splitting '{input_path.name}' ({total_pages} pages) into {num_chunks} chunks "
        f"(up to {chunk_size} pages each)..."
    )
    
    for i in range(num_chunks):
        start_p = i * chunk_size + 1
        end_p = min((i + 1) * chunk_size, total_pages)
        chunk_page_count = (end_p - start_p) + 1
        
        # Zero-padded chunk filename
        chunk_filename = f"{stem}__chunk_{i + 1:02d}_p{start_p}-p{end_p}.pdf"
        chunk_filepath = output_dir / chunk_filename
        
        # Create sub-document for this range
        chunk_doc = fitz.open()
        # fitz uses 0-based indexing: [start_p - 1, end_p - 1]
        chunk_doc.insert_pdf(doc, from_page=start_p - 1, to_page=end_p - 1)
        chunk_doc.save(str(chunk_filepath))
        chunk_doc.close()
        
        chunks.append(
            PDFChunk(
                chunk_index=i + 1,
                start_page=start_p,
                end_page=end_p,
                total_chunks=num_chunks,
                chunk_path=chunk_filepath,
                page_count=chunk_page_count
            )
        )
    
    doc.close()
    logger.info(f"Successfully created {len(chunks)} PDF chunks in {output_dir}")
    return chunks
