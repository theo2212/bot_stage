import fitz  # PyMuPDF
import os

def extract_text_from_pdf(pdf_path):
    """Extracts all text from a PDF file."""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found at {pdf_path}")
    
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    
    return text

def ensure_folders_exist(folders):
    """Creates folders if they don't exist."""
    for folder in folders:
        os.makedirs(folder, exist_ok=True)
