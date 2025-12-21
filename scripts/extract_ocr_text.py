#!/usr/bin/env python3
"""
Extract existing OCR text from all .note files for comparison.
Saves to JSON format for easy before/after comparison.
"""

import json
import base64
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import supernotelib as sn


def extract_ocr_from_page(page) -> dict:
    """Extract OCR text from a single page."""
    recogn_text = page.get_recogn_text()

    if not recogn_text or recogn_text == 'None' or len(recogn_text) == 0:
        return {"has_ocr": False, "text": "", "words": []}

    try:
        # Decode base64
        if isinstance(recogn_text, bytes):
            decoded = base64.b64decode(recogn_text).decode('utf-8')
        else:
            decoded = base64.b64decode(recogn_text.encode()).decode('utf-8')

        data = json.loads(decoded)

        # Extract full text and words
        full_text = ""
        words = []
        for elem in data.get('elements', []):
            if elem.get('type') == 'Text':
                full_text = elem.get('label', '')
                words = elem.get('words', [])
                break

        return {
            "has_ocr": True,
            "text": full_text,
            "word_count": len([w for w in words if w.get('label', '').strip()]),
            "raw_data": data
        }
    except Exception as e:
        return {"has_ocr": True, "text": f"[DECODE ERROR: {e}]", "words": []}


def extract_all_ocr(data_path: Path, output_path: Path):
    """Extract OCR from all .note files."""
    results = {}

    note_files = list(data_path.rglob("*.note"))
    print(f"Found {len(note_files)} .note files")

    for note_path in sorted(note_files):
        rel_path = str(note_path.relative_to(data_path))
        print(f"Processing: {rel_path}")

        try:
            notebook = sn.load_notebook(str(note_path))
            pages = []

            for i, page in enumerate(notebook.pages):
                page_ocr = extract_ocr_from_page(page)
                pages.append({
                    "page": i,
                    **page_ocr
                })

            results[rel_path] = {
                "total_pages": len(notebook.pages),
                "pages_with_ocr": sum(1 for p in pages if p["has_ocr"]),
                "total_text_length": sum(len(p.get("text", "")) for p in pages),
                "pages": pages
            }

        except Exception as e:
            print(f"  ERROR: {e}")
            results[rel_path] = {"error": str(e)}

    # Save results
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nSaved OCR extraction to: {output_path}")

    # Summary
    total_files = len(results)
    files_with_ocr = sum(1 for r in results.values() if r.get("pages_with_ocr", 0) > 0)
    total_chars = sum(r.get("total_text_length", 0) for r in results.values())
    print(f"Summary: {total_files} files, {files_with_ocr} with OCR, {total_chars:,} total characters")


if __name__ == "__main__":
    import sys
    # Use container paths (mounted volumes)
    data_path = Path("/supernote/data")

    # Allow specifying output filename
    output_name = sys.argv[1] if len(sys.argv) > 1 else "ocr-before.json"
    output_path = Path(f"/app/data/{output_name}")

    extract_all_ocr(data_path, output_path)
