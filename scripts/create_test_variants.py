#!/usr/bin/env python3
"""
Create TEST variants with different bbox coordinate transformations.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import base64
import json
import logging
from dataclasses import dataclass
from typing import List

import supernotelib as sn
from note_processor import (
    load_notebook, extract_page, reconstruct_with_recognition,
    pack_pages_with_recognition
)
from ocr_client import OCRClient, TextBlock, OCRResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_variant_with_transform(
    source_path: Path,
    dest_path: Path,
    transform_name: str,
    transform_func
):
    """Create a variant with a specific coordinate transform."""
    print(f"\n{'='*60}")
    print(f"Creating {dest_path.name}: {transform_name}")
    print('='*60)

    # Load source
    notebook = load_notebook(source_path)
    page_data = extract_page(notebook, 0)

    # Run Vision OCR
    ocr_client = OCRClient("http://host.docker.internal:8100")
    ocr_result = ocr_client.ocr_image_vision(page_data.png_bytes)

    print(f"Found {len(ocr_result.text_blocks)} text blocks")

    # Transform coordinates
    transformed_blocks = []
    for block in ocr_result.text_blocks:
        left, top, right, bottom = block.bbox

        # Apply transform
        new_left, new_top, new_right, new_bottom = transform_func(
            left, top, right, bottom, page_data.width, page_data.height
        )

        new_block = TextBlock(
            text=block.text,
            bbox=[new_left, new_top, new_right, new_bottom],
            confidence=block.confidence
        )
        transformed_blocks.append(new_block)

        width_orig = right - left
        height_orig = bottom - top
        width_new = new_right - new_left
        height_new = new_bottom - new_top

        print(f"  \"{block.text}\":")
        print(f"    Original: [{left:.1f}, {top:.1f}, {right:.1f}, {bottom:.1f}] " +
              f"(w={width_orig:.1f}, h={height_orig:.1f})")
        print(f"    Transformed: [{new_left:.1f}, {new_top:.1f}, {new_right:.1f}, {new_bottom:.1f}] " +
              f"(w={width_new:.1f}, h={height_new:.1f})")

    # Create new OCR result with transformed boxes
    transformed_result = OCRResult(
        text_blocks=transformed_blocks,
        full_text=ocr_result.full_text,
        processing_time_ms=ocr_result.processing_time_ms,
        raw_response=ocr_result.raw_response
    )

    # Convert to Supernote format and inject
    from note_processor import convert_ocr_to_supernote_format, inject_ocr_results

    page_results = {0: (transformed_result, page_data.width, page_data.height)}
    inject_ocr_results(dest_path, page_results, backup_dir=None)

    print(f"✅ Created {dest_path.name}")


def main():
    """Create TEST2, TEST3, TEST4 with different transforms."""
    base = Path("/supernote/data/hays.donald@gmail.com/Supernote/Note")
    source = base / "TEST2.note"  # Already has OCR

    # Transform functions
    def transform_original(l, t, r, b, w, h):
        """No transform - use PNG coordinates as-is (baseline)."""
        return l, t, r, b

    def transform_scale_half(l, t, r, b, w, h):
        """Scale down by 0.5x - test if device expects smaller coordinates."""
        return l * 0.5, t * 0.5, r * 0.5, b * 0.5

    def transform_offset_left_up(l, t, r, b, w, h):
        """Offset left and up by 200px - test if there's a margin/offset."""
        offset_x = -200
        offset_y = -200
        return l + offset_x, t + offset_y, r + offset_x, b + offset_y

    def transform_invert_y(l, t, r, b, w, h):
        """Invert Y axis - test if origin is bottom-left instead of top-left."""
        new_t = h - b
        new_b = h - t
        return l, new_t, r, new_b

    # Create TEST from scratch (fresh baseline)
    test1 = base / "TEST.note"
    test2 = base / "TEST2.note"
    test3 = base / "TEST3.note"
    test4 = base / "TEST4.note"

    # TEST2 already exists with original transform - just verify
    print("\n" + "="*60)
    print("TEST2.note: Original PNG coordinates (BASELINE)")
    print("="*60)
    notebook = load_notebook(test2)
    page = notebook.pages[0]
    recogn_text = page.get_recogn_text()
    if recogn_text and recogn_text != 'None':
        decoded = base64.b64decode(recogn_text).decode('utf-8')
        data = json.loads(decoded)
        for elem in data.get('elements', []):
            if elem.get('type') == 'Text':
                for word in elem.get('words', []):
                    if 'bounding-box' in word and word.get('label', '').strip():
                        bbox = word['bounding-box']
                        print(f"  \"{word['label']}\": x={bbox['x']}, y={bbox['y']}, " +
                              f"w={bbox['width']}, h={bbox['height']}")

    # Create TEST3: scaled down
    create_variant_with_transform(
        test1, test3,
        "Scaled 0.5x (half size)",
        transform_scale_half
    )

    # Create TEST4: inverted Y
    create_variant_with_transform(
        test1, test4,
        "Y-axis inverted (bottom-left origin)",
        transform_invert_y
    )

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print("TEST.note  - Original (no OCR) - KEEP AS REFERENCE")
    print("TEST2.note - PNG coordinates as-is (CURRENT/BASELINE)")
    print("TEST3.note - Scaled 0.5x (test if device expects smaller coords)")
    print("TEST4.note - Y-inverted (test if origin is bottom-left)")
    print("\nSync and test highlighting on each file!")


if __name__ == "__main__":
    main()
