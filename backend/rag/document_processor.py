import os
from typing import List
from PyPDF2 import PdfReader
from loguru import logger

def extract_text_from_pdf(file_path: str) -> str:
    try:
        reader = PdfReader(file_path)
        text = ""
        for idx, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                text += f"\n--- Page {idx + 1} ---\n" + page_text
        return text
    except Exception as e:
        logger.error(f"Error reading PDF file {file_path}: {e}")
        raise e

def extract_text_from_txt(file_path: str) -> str:
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error reading TXT file {file_path}: {e}")
        raise e

def extract_text(file_path: str) -> str:
    _, ext = os.path.splitext(file_path.lower())
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext in [".txt", ".md", ".json", ".csv"]:
        return extract_text_from_txt(file_path)
    else:
        # Fallback to try reading as plain text
        try:
            return extract_text_from_txt(file_path)
        except Exception:
            raise ValueError(f"Unsupported file extension: {ext}")

def chunk_text(text: str, chunk_size: int = 600, overlap: int = 60) -> List[str]:
    """
    Split text into chunks of roughly `chunk_size` characters with `overlap` overlap.
    A simple but highly functional sliding window chunker.
    """
    if not text:
        return []
        
    chunks = []
    start = 0
    text_len = len(text)
    
    while start < text_len:
        # Define end index
        end = start + chunk_size
        if end >= text_len:
            chunks.append(text[start:])
            break
            
        # Try to find a logical break point (newline or space) near the end to keep text coherent
        break_point = text.rfind("\n", start + chunk_size - 100, end)
        if break_point == -1 or break_point <= start:
            break_point = text.rfind(" ", start + chunk_size - 50, end)
            
        if break_point != -1 and break_point > start:
            end = break_point + 1 # Include the space or newline
            
        chunks.append(text[start:end])
        # Advance by chunk_size minus overlap
        start = end - overlap
        if start >= text_len or overlap >= chunk_size:
            break
            
    return [c.strip() for c in chunks if c.strip()]
