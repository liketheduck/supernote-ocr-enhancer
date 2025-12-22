"""
Supernote .note file processor.
Handles page extraction, OCR integration, and writing recognition data back.
"""

import io
import os
import base64
import json
import logging
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime

from PIL import Image
import supernotelib as sn
import supernotelib.manipulator as manip
import supernotelib.parser as parser

from ocr_client import OCRResult, TextBlock

logger = logging.getLogger(__name__)


@dataclass
class PageData:
    """Data for a single page."""
    page_number: int
    png_bytes: bytes
    image: Image.Image
    width: int
    height: int


@dataclass
class NotebookInfo:
    """Information about a .note file."""
    path: Path
    total_pages: int
    is_realtime_recognition: bool
    file_type: str


def load_notebook(note_path: Path) -> sn.Notebook:
    """Load a .note file."""
    return sn.load_notebook(str(note_path))


def get_notebook_info(note_path: Path) -> NotebookInfo:
    """Get metadata about a .note file."""
    notebook = load_notebook(note_path)
    return NotebookInfo(
        path=note_path,
        total_pages=len(notebook.pages),
        is_realtime_recognition=notebook.is_realtime_recognition(),
        file_type=notebook.type if hasattr(notebook, 'type') else 'unknown'
    )


def extract_page(notebook: sn.Notebook, page_number: int) -> PageData:
    """
    Extract a single page as PNG image.

    Args:
        notebook: Loaded notebook object
        page_number: Page index (0-based)

    Returns:
        PageData with image bytes and dimensions
    """
    converter = sn.converter.ImageConverter(notebook)
    img = converter.convert(page_number)

    # Convert to PNG bytes
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    png_bytes = buf.getvalue()

    return PageData(
        page_number=page_number,
        png_bytes=png_bytes,
        image=img,
        width=img.size[0],
        height=img.size[1]
    )


def extract_all_pages(notebook: sn.Notebook) -> List[PageData]:
    """Extract all pages from a notebook."""
    pages = []
    for i in range(len(notebook.pages)):
        try:
            page_data = extract_page(notebook, i)
            pages.append(page_data)
        except Exception as e:
            logger.error(f"Failed to extract page {i}: {e}")
    return pages


def convert_ocr_to_supernote_format(
    ocr_result: OCRResult,
    original_width: int,
    original_height: int
) -> bytes:
    """
    Convert OCR result to Supernote's recognition format (base64-encoded JSON).

    The Supernote format:
    {
        "elements": [
            {"type": "Raw Content"},
            {
                "type": "Text",
                "label": "full text",
                "words": [
                    {"bounding-box": {"x": ..., "y": ..., "width": ..., "height": ...}, "label": "word"},
                    {"label": " "},
                    ...
                ]
            }
        ],
        "type": "Text"
    }

    CRITICAL: Supernote uses a scaled coordinate system!
    - Vision Framework returns bboxes in PNG pixels (e.g., x=420, y=711)
    - Supernote expects coordinates divided by 11.9 (e.g., x=35.3, y=59.7)
    - This scaling factor was empirically determined by comparing device OCR to Vision OCR
    - Without this scaling, search highlighting appears in wrong positions
    """
    # Supernote coordinate scaling factor (discovered via device OCR analysis)
    SUPERNOTE_SCALE_FACTOR = 11.9

    words = []

    # Vision Framework returns word-level text blocks with bboxes in PNG pixels
    # bbox format: [left, top, right, bottom] in pixels
    for i, block in enumerate(ocr_result.text_blocks):
        text = block.text.strip()
        if not text:
            continue

        # bbox format: [left, top, right, bottom] in PNG pixels
        left, top, right, bottom = block.bbox

        # Convert to Supernote's scaled coordinate system
        # Divide by 11.9 to match device's native coordinate system
        x = float(left) / SUPERNOTE_SCALE_FACTOR
        y = float(top) / SUPERNOTE_SCALE_FACTOR
        width = float(right - left) / SUPERNOTE_SCALE_FACTOR
        height = float(bottom - top) / SUPERNOTE_SCALE_FACTOR

        # Each block from Vision is already a word (or word group)
        words.append({
            "bounding-box": {
                "x": round(x, 2),
                "y": round(y, 2),
                "width": round(width, 2),
                "height": round(height, 2)
            },
            "label": text
        })

        # Add space after each word (except last)
        if i < len(ocr_result.text_blocks) - 1:
            words.append({"label": " "})

    recogn_data = {
        "elements": [
            {"type": "Raw Content"},
            {
                "type": "Text",
                "label": ocr_result.full_text,
                "words": words
            }
        ],
        "type": "Text"
    }

    # Encode as base64
    json_str = json.dumps(recogn_data, ensure_ascii=False)
    return base64.b64encode(json_str.encode('utf-8'))


def pack_pages_with_recognition(builder, notebook, offset=0):
    """
    Modified _pack_pages that includes recognition data.
    This is a patched version that properly packs RECOGNTEXT blocks.
    """
    for i in range(notebook.get_total_pages()):
        page_number = i + 1 + offset
        original_page = notebook.get_page(i)
        page = manip.utils.WorkaroundPageWrapper.from_page(original_page)

        # Pack layers (same as original)
        layers = page.get_layers()
        for layer in layers:
            layer_name = layer.get_name()
            if layer_name is None:
                continue
            if layer_name == 'BGLAYER':
                style = page.get_style()
                if style.startswith('user_'):
                    style += page.get_style_hash()
                layer_metadata = layer.metadata
                layer_metadata['LAYERNAME'] = layer_name
                layer_metadata['LAYERBITMAP'] = str(builder.get_block_address(f'STYLE_{style}'))
                layer_metadata_block = manip._construct_metadata_block(layer_metadata)
                builder.append(f'PAGE{page_number}/{layer_name}/metadata', layer_metadata_block)
            else:
                content = layer.get_content()
                builder.append(f'PAGE{page_number}/{layer_name}/LAYERBITMAP', content)
                layer_metadata = layer.metadata
                layer_metadata['LAYERNAME'] = layer_name
                layer_metadata['LAYERBITMAP'] = str(builder.get_block_address(f'PAGE{page_number}/{layer_name}/LAYERBITMAP'))
                layer_metadata_block = manip._construct_metadata_block(layer_metadata)
                builder.append(f'PAGE{page_number}/{layer_name}/metadata', layer_metadata_block)

        # Pack totalpath
        totalpath_block = page.get_totalpath()
        if totalpath_block is not None:
            builder.append(f'PAGE{page_number}/TOTALPATH', totalpath_block)

        # Get recognition from ORIGINAL page (not wrapper!)
        recogn_text = original_page.get_recogn_text()
        recogn_file = original_page.get_recogn_file()

        # Add recognition blocks if present
        if recogn_text and recogn_text != 'None' and len(recogn_text) > 0:
            if isinstance(recogn_text, str):
                recogn_text = recogn_text.encode('utf-8')
            builder.append(f'PAGE{page_number}/RECOGNTEXT', recogn_text)
            logger.debug(f"Added RECOGNTEXT block for page {page_number}")

        if recogn_file and len(recogn_file) > 0:
            builder.append(f'PAGE{page_number}/RECOGNFILE', recogn_file)

        # Build page metadata
        page_metadata = dict(page.metadata)
        del page_metadata['__layers__']

        for prop in ['MAINLAYER', 'LAYER1', 'LAYER2', 'LAYER3', 'BGLAYER']:
            address = builder.get_block_address(f'PAGE{page_number}/{prop}/metadata')
            page_metadata[prop] = address

        page_metadata['TOTALPATH'] = builder.get_block_address(f'PAGE{page_number}/TOTALPATH')

        # Update recognition addresses
        recogn_text_addr = builder.get_block_address(f'PAGE{page_number}/RECOGNTEXT')
        recogn_file_addr = builder.get_block_address(f'PAGE{page_number}/RECOGNFILE')

        if recogn_text_addr > 0:
            page_metadata['RECOGNTEXT'] = recogn_text_addr
            page_metadata['RECOGNSTATUS'] = 1  # Mark as DONE

        if recogn_file_addr > 0:
            page_metadata['RECOGNFILE'] = recogn_file_addr

        page_metadata_block = manip._construct_metadata_block(page_metadata)
        builder.append(f'PAGE{page_number}/metadata', page_metadata_block)


def reconstruct_with_recognition(notebook: sn.Notebook, enable_highlighting: bool = True) -> bytes:
    """
    Reconstruct a notebook binary with recognition data.

    This is a modified version of sn.reconstruct() that properly
    includes recognition text blocks and enables search highlighting.

    IMPORTANT: Uses FILE_RECOGN_TYPE='0' to preserve OCR data!
    - TYPE='0' enables highlighting while preventing device from re-OCRing
    - TYPE='1' would cause device to overwrite our OCR after pen strokes
    - This saves battery life and preserves our high-quality Vision OCR

    Args:
        notebook: The notebook to reconstruct
        enable_highlighting: If True, set FILE_RECOGN_TYPE to '0' to enable
            search highlighting while preventing device re-OCR (default: True)
    """
    expected_signature = parser.SupernoteXParser.SN_SIGNATURES[-1]
    metadata = notebook.get_metadata()

    if metadata.signature != expected_signature:
        raise ValueError(
            f'Only latest file format version is supported '
            f'({metadata.signature} != {expected_signature})'
        )

    # Set recognition language and type (both required for highlighting)
    if hasattr(metadata, 'header') and isinstance(metadata.header, dict):
        # Set language to en_US (required for device to use OCR data)
        if metadata.header.get('FILE_RECOGN_LANGUAGE') != 'en_US':
            logger.info("Setting recognition language (FILE_RECOGN_LANGUAGE -> en_US)")
            metadata.header['FILE_RECOGN_LANGUAGE'] = 'en_US'

        # Enable recognition for search highlighting
        # TYPE='0' enables highlighting while preventing device from re-OCRing
        # This preserves our Vision OCR and saves battery life
        if enable_highlighting:
            logger.info("Enabling search highlighting (FILE_RECOGN_TYPE -> 0)")
            metadata.header['FILE_RECOGN_TYPE'] = '0'

    builder = manip.NotebookBuilder()
    manip._pack_type(builder, notebook)
    manip._pack_signature(builder, notebook)
    manip._pack_header(builder, notebook)
    manip._pack_cover(builder, notebook)
    manip._pack_keywords(builder, notebook)
    manip._pack_titles(builder, notebook)
    manip._pack_links(builder, notebook)
    manip._pack_backgrounds(builder, notebook)

    # Use our modified packer
    pack_pages_with_recognition(builder, notebook)

    manip._pack_footer(builder)
    manip._pack_tail(builder)
    manip._pack_footer_address(builder)

    reconstructed = builder.build()

    # Validate the reconstructed file
    stream = io.BytesIO(reconstructed)
    xparser = parser.SupernoteXParser()
    try:
        _ = xparser.parse_stream(stream)
    except Exception as e:
        raise ValueError(f'Generated file fails validation: {e}')

    return reconstructed


def inject_ocr_results(
    note_path: Path,
    page_results: Dict[int, Tuple[OCRResult, int, int]],
    backup_dir: Optional[Path] = None
) -> bool:
    """
    Inject OCR results into a .note file.

    Args:
        note_path: Path to the .note file
        page_results: Dict mapping page_number -> (OCRResult, image_width, image_height)
        backup_dir: Optional directory for backups

    Returns:
        True if successful
    """
    # Create backup
    if backup_dir:
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{note_path.stem}_{timestamp}.note.bak"
        shutil.copy2(note_path, backup_path)
        logger.info(f"Created backup: {backup_path}")

    # Load notebook
    notebook = load_notebook(note_path)

    # Set recognition text for each page
    for page_num, (ocr_result, width, height) in page_results.items():
        if page_num >= len(notebook.pages):
            logger.warning(f"Page {page_num} out of range, skipping")
            continue

        # Convert OCR result to Supernote format
        recogn_data = convert_ocr_to_supernote_format(ocr_result, width, height)

        # Set on the page
        page = notebook.pages[page_num]
        page.set_recogn_text(recogn_data)
        logger.debug(f"Set recognition text for page {page_num}: {len(recogn_data)} bytes")

    # Reconstruct the file
    try:
        reconstructed = reconstruct_with_recognition(notebook)

        # Save original timestamps before writing
        original_stat = note_path.stat()
        original_mtime = original_stat.st_mtime
        original_atime = original_stat.st_atime

        # Write back
        with open(note_path, 'wb') as f:
            f.write(reconstructed)

        # Preserve timestamp: set mtime to original + 60 seconds
        # This keeps the file's timeline intact while indicating it was processed
        new_mtime = original_mtime + 60  # Add 1 minute
        os.utime(note_path, (original_atime, new_mtime))
        logger.debug(f"Preserved timestamp: original + 60s")

        logger.info(f"Successfully wrote OCR data to {note_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to reconstruct {note_path}: {e}")

        # Restore from backup if available
        if backup_dir and backup_path.exists():
            shutil.copy2(backup_path, note_path)
            logger.info("Restored from backup")

        raise


def get_existing_ocr_text(notebook: sn.Notebook, page_number: int) -> Optional[str]:
    """Get existing OCR text from a page, if any."""
    if page_number >= len(notebook.pages):
        return None

    page = notebook.pages[page_number]
    recogn_text = page.get_recogn_text()

    if not recogn_text or recogn_text == 'None':
        return None

    try:
        decoded = base64.b64decode(recogn_text).decode('utf-8')
        data = json.loads(decoded)
        # Extract the label (full text)
        for elem in data.get('elements', []):
            if elem.get('type') == 'Text':
                return elem.get('label', '')
        return None
    except Exception:
        return None
