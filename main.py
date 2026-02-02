import os
import pdfplumber
import yaml
import re
from fastapi import FastAPI, File, UploadFile, HTTPException
import shutil
import tempfile


def extract_text_with_pdfplumber(pdf_path):
    pages_content = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text(x_tolerance=2, y_tolerance=2)
                if not page_text:
                    page_text = "[No text found on this page]"
                
                pages_content.append({
                    "pagenumber": i + 1,
                    "raw_text": page_text
                })
        return pages_content
    except Exception as e:
        print(f"Error extracting {pdf_path}: {e}")
        return []



def find_all_pdfs(start_dir="."):
    pdf_files = []
    for root, _, files in os.walk(start_dir):
        for file in files:
            if file.lower().endswith(".pdf"):
                pdf_files.append(os.path.join(root, file))
    return pdf_files


def get_unique_output_name(pdf_path, output_dir):
    base_name = os.path.basename(pdf_path)
    parent_folder = os.path.basename(os.path.dirname(os.path.abspath(pdf_path)))
    safe_name = f"{parent_folder}_{os.path.splitext(base_name)[0]}.txt"
    return os.path.join(output_dir, safe_name)



def load_header_config(config_path="header_config.yaml"):
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)



def normalize_headers(text, config):
    canonical_fields = config.get("canonical_fields", {})
    options = config.get("options", {})

    case_insensitive = options.get("case_insensitive", True)
    whole_word_match = options.get("whole_word_match", True)

    for canonical_name, field_data in canonical_fields.items():
        aliases = field_data.get("aliases", [])

        for alias in aliases:
            if whole_word_match:
                pattern = r"\b{}\b".format(re.escape(alias))
            else:
                pattern = re.escape(alias)

            flags = re.IGNORECASE if case_insensitive else 0
            text = re.sub(pattern, canonical_name, text, flags=flags)

    return text



app = FastAPI()

@app.post("/extract")
async def extract_text_endpoint(file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    
    try:
        pages = extract_text_with_pdfplumber(tmp_path)
        
        try:
            config = load_header_config()
        except FileNotFoundError:
             config = {"canonical_fields": {}, "options": {}}

        for page in pages:
            page["raw_text"] = normalize_headers(page["raw_text"], config)
        
        return {"filename": file.filename, "pages": pages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

if __name__ == "__main__":

    base_dir = "."
    output_dir = "extracted_texts_pdfplumber"
    config_path = "header_config.yaml"

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print(f"Searching for PDFs in {os.path.abspath(base_dir)}...")

    pdfs = find_all_pdfs(base_dir)

    if not pdfs:
        print("No PDFs found.")
        exit()

    print(f"Found {len(pdfs)} PDF(s). Loading header config...\n")

    config = load_header_config(config_path)

    for pdf_file in pdfs:
        output_path = get_unique_output_name(pdf_file, output_dir)
        print(f"Processing: {pdf_file} -> {output_path}")

        pages = extract_text_with_pdfplumber(pdf_file)
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"Source: {pdf_file}\n")
            f.write("=" * 40 + "\n\n")
            
            for page in pages:
                normalized_text = normalize_headers(page["raw_text"], config)
                f.write(f"--- Page {page['pagenumber']} ---\n")
                f.write(normalized_text + "\n")

    print("\n✅ Extraction and header normalization completed.")
