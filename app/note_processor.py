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
import re

logger = logging.getLogger(__name__)


def pack_footer_preserving_extras(builder, notebook):
    """
    Custom footer packer that preserves extra fields like DIRTY.

    The standard manip._pack_footer() rebuilds the footer from scratch,
    losing fields like DIRTY which may affect device behavior (e.g.,
    which page to open on resume).
    """
    metadata = notebook.get_metadata()
    original_footer = metadata.footer if hasattr(metadata, 'footer') else {}

    # Build footer the same way as manip._pack_footer
    metadata_footer = {}
    metadata_footer.setdefault('FILE_FEATURE', builder.get_block_address('__header__'))

    for label in builder.get_labels():
        if re.match(r'PAGE\d+/metadata', label):
            address = builder.get_block_address(label)
            label = label[:-len('/metadata')]
            metadata_footer.setdefault(label, address)

    for label in builder.get_labels():
        if re.match(r'TITLE_\d+/metadata', label):
            address_list = builder.get_duplicate_block_address_list(label)
            label = label[:-len('/metadata')]
            if len(address_list) == 1:
                metadata_footer.setdefault(label, address_list[0])
            else:
                metadata_footer[label] = address_list

    for label in builder.get_labels():
        if re.match(r'KEYWORD_\d+/metadata', label):
            address_list = builder.get_duplicate_block_address_list(label)
            label = label[:-len('/metadata')]
            if len(address_list) == 1:
                metadata_footer.setdefault(label, address_list[0])
            else:
                metadata_footer[label] = address_list

    for label in builder.get_labels():
        if re.match(r'LINKO_\d+/metadata', label):
            address_list = builder.get_duplicate_block_address_list(label)
            label = label[:-len('/metadata')]
            if len(address_list) == 1:
                metadata_footer.setdefault(label, address_list[0])
            else:
                metadata_footer[label] = address_list

    address = builder.get_block_address('COVER_2')
    if address == 0:
        metadata_footer['COVER_0'] = 0
    else:
        metadata_footer['COVER_2'] = address

    for label in builder.get_labels():
        if label.startswith('STYLE_'):
            address = builder.get_block_address(label)
            metadata_footer.setdefault(label, address)

    # Preserve DIRTY from original footer (affects device page resume behavior)
    if 'DIRTY' in original_footer:
        metadata_footer['DIRTY'] = original_footer['DIRTY']
        logger.debug(f"Preserving footer DIRTY={original_footer['DIRTY']}")

    footer_block = manip._construct_metadata_block(metadata_footer)
    builder.append('__footer__', footer_block)


@dataclass
class PageData:
    """Data for a single page."""
    page_number: int
    png_bytes: bytes
    image: Image.Image
    width: int
    height: int
    from_bglayer: bool = False  # True if extracted from PDF/custom background layer


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


def _extract_bglayer_png(notebook: sn.Notebook, page_number: int) -> Optional[PageData]:
    """
    Extract PNG directly from BGLAYER for pages with custom backgrounds.

    Some .note files (e.g., those created with PDF imports) store the page
    image directly as a PNG in the BGLAYER. This bypasses supernotelib's
    converter which doesn't support these custom formats.

    Args:
        notebook: Loaded notebook object
        page_number: Page index (0-based)

    Returns:
        PageData if BGLAYER contains a valid PNG, None otherwise
    """
    try:
        page = notebook.get_page(page_number)
        style = page.get_style() if hasattr(page, 'get_style') else None

        # Only try this for custom user styles (PDF imports, etc.)
        if not style or not style.startswith('user_'):
            return None

        # Look for PNG in BGLAYER
        for layer in page.get_layers():
            if layer.get_name() == 'BGLAYER':
                content = layer.get_content()
                if content and len(content) > 8 and content[:4] == b'\x89PNG':
                    # It's a PNG! Load it directly
                    img = Image.open(io.BytesIO(content))

                    # Convert to RGB if needed (OCR expects RGB)
                    if img.mode != 'RGB':
                        img = img.convert('RGB')

                    # Convert to PNG bytes
                    buf = io.BytesIO()
                    img.save(buf, format='PNG')
                    png_bytes = buf.getvalue()

                    logger.debug(f"Extracted PNG from BGLAYER for page {page_number} "
                                f"(custom style: {style}, {img.size[0]}x{img.size[1]})")

                    return PageData(
                        page_number=page_number,
                        png_bytes=png_bytes,
                        image=img,
                        width=img.size[0],
                        height=img.size[1],
                        from_bglayer=True
                    )
        return None
    except Exception as e:
        logger.debug(f"BGLAYER extraction failed for page {page_number}: {e}")
        return None


def extract_page(notebook: sn.Notebook, page_number: int, ocr_pdf_layers: bool = True) -> PageData:
    """
    Extract a single page as PNG image.

    Args:
        notebook: Loaded notebook object
        page_number: Page index (0-based)
        ocr_pdf_layers: If True, attempt to extract embedded PNGs from custom
                        backgrounds (PDF imports) when normal extraction fails

    Returns:
        PageData with image bytes and dimensions

    Raises:
        Exception if page cannot be extracted
    """
    try:
        # Try standard converter first
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
    except Exception as e:
        # If standard extraction fails and PDF layer OCR is enabled,
        # try extracting from BGLAYER directly
        if ocr_pdf_layers:
            bglayer_result = _extract_bglayer_png(notebook, page_number)
            if bglayer_result:
                logger.info(f"  Page {page_number}: extracted from BGLAYER (PDF/custom layer)")
                return bglayer_result

        # Re-raise original error if fallback didn't work
        raise


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


def _group_words_into_lines(text_blocks: List, line_threshold_ratio: float = 0.5) -> List[List]:
    """
    Group text blocks into lines based on Y-coordinate proximity.

    Args:
        text_blocks: List of TextBlock objects with bbox [left, top, right, bottom]
        line_threshold_ratio: Fraction of average word height to use as line break threshold

    Returns:
        List of lines, where each line is a list of TextBlock objects sorted left-to-right
    """
    if not text_blocks:
        return []

    # Filter out empty blocks and get valid ones with their Y coordinates
    valid_blocks = [(block, block.bbox[1]) for block in text_blocks if block.text.strip()]
    if not valid_blocks:
        return []

    # Sort by Y coordinate (top to bottom)
    valid_blocks.sort(key=lambda x: x[1])

    # Calculate average word height for threshold
    heights = [block.bbox[3] - block.bbox[1] for block, _ in valid_blocks]
    avg_height = sum(heights) / len(heights) if heights else 20
    line_threshold = avg_height * line_threshold_ratio

    # Group into lines
    lines = []
    current_line = [valid_blocks[0][0]]
    current_y = valid_blocks[0][1]

    for block, y in valid_blocks[1:]:
        # If Y coordinate differs by more than threshold, start new line
        if abs(y - current_y) > line_threshold:
            # Sort current line by X coordinate before adding
            current_line.sort(key=lambda b: b.bbox[0])
            lines.append(current_line)
            current_line = [block]
            current_y = y
        else:
            current_line.append(block)
            # Update current_y to average of line (helps with slight variations)
            current_y = (current_y + y) / 2

    # Don't forget the last line
    if current_line:
        current_line.sort(key=lambda b: b.bbox[0])
        lines.append(current_line)

    return lines


def convert_ocr_to_supernote_format(
    ocr_result: OCRResult,
    original_width: int,
    original_height: int
) -> bytes:
    """
    Convert OCR result to Supernote's recognition format (base64-encoded JSON).

    The Supernote format supports multiple Text elements for line breaks:
    {
        "elements": [
            {"type": "Raw Content"},
            {"type": "Text", "label": "line 1 text", "words": [...]},
            {"type": "Text", "label": "line 2 text", "words": [...]},
            ...
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

    # Group words into lines based on Y-coordinate
    lines = _group_words_into_lines(ocr_result.text_blocks)

    elements = [{"type": "Raw Content"}]
    line_texts = []

    for line_blocks in lines:
        words = []
        line_text_parts = []

        for i, block in enumerate(line_blocks):
            text = block.text.strip()
            if not text:
                continue

            line_text_parts.append(text)

            # bbox format: [left, top, right, bottom] in PNG pixels
            left, top, right, bottom = block.bbox

            # Convert to Supernote's scaled coordinate system
            x = float(left) / SUPERNOTE_SCALE_FACTOR
            y = float(top) / SUPERNOTE_SCALE_FACTOR
            width = float(right - left) / SUPERNOTE_SCALE_FACTOR
            height = float(bottom - top) / SUPERNOTE_SCALE_FACTOR

            words.append({
                "bounding-box": {
                    "x": round(x, 2),
                    "y": round(y, 2),
                    "width": round(width, 2),
                    "height": round(height, 2)
                },
                "label": text
            })

            # Add space after each word (except last in line)
            if i < len(line_blocks) - 1:
                words.append({"label": " "})

        if words:
            line_text = " ".join(line_text_parts)
            line_texts.append(line_text)
            elements.append({
                "type": "Text",
                "label": line_text,
                "words": words
            })

    # Build full text with newlines between lines
    full_text_with_breaks = "\n".join(line_texts)

    recogn_data = {
        "elements": elements,
        "type": "Text"
    }

    # Encode as base64
    json_str = json.dumps(recogn_data, ensure_ascii=False)
    logger.debug(f"Generated recognition data: {len(lines)} lines, {len(full_text_with_breaks)} chars")
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


def reconstruct_with_recognition(notebook: sn.Notebook, recogn_type: str = "1") -> bytes:
    """
    Reconstruct a notebook binary with recognition data.

    This is a modified version of sn.reconstruct() that properly
    includes recognition text blocks and enables search highlighting.

    FILE_RECOGN_TYPE controls REALTIME recognition during writing:
    - TYPE='1' = realtime recognition ON = device performs OCR while you write
    - TYPE='0' = realtime recognition OFF = device doesn't do realtime OCR

    IMPORTANT: Both TYPE values allow searching existing OCR data!
    Files with TYPE='0' are still searchable if they have RECOGNTEXT data.
    TYPE only controls whether device adds NEW OCR while writing.

    Args:
        notebook: The notebook to reconstruct
        recogn_type: FILE_RECOGN_TYPE value to set:
            - "0" = disable device realtime OCR
            - "1" = enable device realtime OCR (default)
            - "keep" = preserve existing value from file
    """
    expected_signature = parser.SupernoteXParser.SN_SIGNATURES[-1]
    metadata = notebook.get_metadata()

    if metadata.signature != expected_signature:
        raise ValueError(
            f'Only latest file format version is supported '
            f'({metadata.signature} != {expected_signature})'
        )

    # Set recognition language and type
    if hasattr(metadata, 'header') and isinstance(metadata.header, dict):
        # Set language to en_US (required for device to use OCR data)
        if metadata.header.get('FILE_RECOGN_LANGUAGE') != 'en_US':
            logger.info("Setting recognition language (FILE_RECOGN_LANGUAGE -> en_US)")
            metadata.header['FILE_RECOGN_LANGUAGE'] = 'en_US'

        # Handle FILE_RECOGN_TYPE based on user preference
        # TYPE='1' = device performs OCR while writing
        # TYPE='0' = no realtime OCR, but existing OCR data still searchable
        current_type = metadata.header.get('FILE_RECOGN_TYPE', '1')
        if recogn_type == "keep":
            logger.debug(f"Keeping existing FILE_RECOGN_TYPE={current_type}")
        elif recogn_type in ("0", "1"):
            if current_type != recogn_type:
                logger.info(f"Setting FILE_RECOGN_TYPE: {current_type} -> {recogn_type}")
                metadata.header['FILE_RECOGN_TYPE'] = recogn_type
        else:
            logger.warning(f"Invalid recogn_type '{recogn_type}', defaulting to '1'")
            metadata.header['FILE_RECOGN_TYPE'] = '1'

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

    # Use our custom footer packer that preserves DIRTY flag
    pack_footer_preserving_extras(builder, notebook)
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
    backup_dir: Optional[Path] = None,
    recogn_type: str = "1"
) -> bool:
    """
    Inject OCR results into a .note file.

    Args:
        note_path: Path to the .note file
        page_results: Dict mapping page_number -> (OCRResult, image_width, image_height)
        backup_dir: Optional directory for backups
        recogn_type: FILE_RECOGN_TYPE setting ("0", "1", or "keep")

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
        reconstructed = reconstruct_with_recognition(notebook, recogn_type=recogn_type)

        # Save original timestamps before writing
        original_stat = note_path.stat()
        original_mtime = original_stat.st_mtime
        original_atime = original_stat.st_atime

        # Write back
        with open(note_path, 'wb') as f:
            f.write(reconstructed)

        # Preserve timestamp: set mtime to original + 1 second
        # This keeps the file's timeline intact while indicating it was processed
        # 1 second is sufficient to win sync (MD5 also changes, so timestamp just needs to be newer)
        new_mtime = original_mtime + 1  # Add 1 second
        os.utime(note_path, (original_atime, new_mtime))
        logger.debug(f"Preserved timestamp: original + 1s")

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
