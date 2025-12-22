#!/usr/bin/env python3
"""
Diagnose bounding box issues by visualizing OCR results.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import json
import base64
from PIL import Image, ImageDraw, ImageFont
import supernotelib as sn
from note_processor import extract_page, load_notebook
from ocr_client import OCRClient

def diagnose_file(note_path: Path, output_dir: Path):
    """Diagnose bbox issues for a .note file."""
    print(f"\n{'='*60}")
    print(f"Diagnosing: {note_path.name}")
    print('='*60)

    # Load and extract
    notebook = load_notebook(note_path)
    page_data = extract_page(notebook, 0)

    print(f"Page dimensions: {page_data.width}x{page_data.height}")

    # Save original image
    orig_img_path = output_dir / f"{note_path.stem}_original.png"
    page_data.image.save(orig_img_path)
    print(f"Saved: {orig_img_path}")

    # Run Vision OCR
    ocr_client = OCRClient("http://host.docker.internal:8100")
    ocr_result = ocr_client.ocr_image_vision(page_data.png_bytes)

    print(f"\nVision OCR found {len(ocr_result.text_blocks)} blocks:")

    # Draw bboxes on image
    img_with_boxes = page_data.image.copy()
    draw = ImageDraw.Draw(img_with_boxes)

    for i, block in enumerate(ocr_result.text_blocks):
        left, top, right, bottom = block.bbox
        width = right - left
        height = bottom - top

        print(f"\n  Block {i+1}: \"{block.text}\"")
        print(f"    Vision bbox: [{left:.1f}, {top:.1f}, {right:.1f}, {bottom:.1f}]")
        print(f"    Size: {width:.1f}x{height:.1f}")

        # Supernote format conversion
        supernote_bbox = {
            "x": round(left, 2),
            "y": round(top, 2),
            "width": round(width, 2),
            "height": round(height, 2)
        }
        print(f"    Supernote: x={supernote_bbox['x']}, y={supernote_bbox['y']}, " +
              f"w={supernote_bbox['width']}, h={supernote_bbox['height']}")

        # Draw red rectangle
        draw.rectangle([left, top, right, bottom], outline="red", width=5)

        # Draw text label
        label = f"{i+1}: {block.text[:20]}"
        draw.text((left, top - 30), label, fill="red")

    # Save annotated image
    annotated_path = output_dir / f"{note_path.stem}_with_bboxes.png"
    img_with_boxes.save(annotated_path)
    print(f"\n✅ Saved annotated image: {annotated_path}")

    # Check if file already has OCR
    page = notebook.pages[0]
    recogn_text = page.get_recogn_text()
    if recogn_text and recogn_text != 'None':
        print(f"\n📋 File already has OCR data")
        decoded = base64.b64decode(recogn_text).decode('utf-8')
        data = json.loads(decoded)

        for elem in data.get('elements', []):
            if elem.get('type') == 'Text':
                words = elem.get('words', [])
                print(f"   Stored words: {len([w for w in words if w.get('label', '').strip()])}")
                break

def main():
    """Diagnose TEST files."""
    note_dir = Path("/supernote/data/hays.donald@gmail.com/Supernote/Note")
    output_dir = Path("/app/data/diagnostics")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Diagnose TEST2
    test_file = note_dir / "TEST2.note"
    if test_file.exists():
        diagnose_file(test_file, output_dir)
    else:
        print(f"❌ {test_file} not found")

if __name__ == "__main__":
    main()
