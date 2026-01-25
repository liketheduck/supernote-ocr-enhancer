"""
PDF export functionality for Supernote notes with embedded OCR layer.

Generates searchable PDFs where:
- Visible layer: Original handwritten note image
- Invisible layer: OCR text with bounding boxes for search/indexing
"""

import io
import logging
from pathlib import Path
from typing import Dict, Tuple, Optional

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from PIL import Image

from ocr_client import OCRResult

logger = logging.getLogger(__name__)


def export_note_to_pdf(
    note_path: Path,
    page_results: Dict[int, Tuple[OCRResult, int, int]],
    supernote_data_path: Path,
    output_base_path: Path,
    debug_mode: bool = False
) -> Optional[Path]:
    """
    Export a Supernote .note file to a searchable PDF.
    
    Args:
        note_path: Path to the .note file
        page_results: Dict mapping page_num to (OCRResult, width, height)
        supernote_data_path: Base path of Supernote data directory
        output_base_path: Base path for PDF exports
        
    Returns:
        Path to the generated PDF, or None if export failed
    """
    try:
        # Calculate relative path to preserve directory structure
        rel_path = note_path.relative_to(supernote_data_path)
        output_path = output_base_path / rel_path.parent / f"{rel_path.stem}.pdf"
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create PDF
        c = canvas.Canvas(str(output_path), pagesize=letter)
        
        # Sort pages by page number
        sorted_pages = sorted(page_results.items())
        
        for page_num, (ocr_result, img_width, img_height) in sorted_pages:
            # Get page image from OCR result
            # Note: We need to re-extract the page image since we don't store it
            from note_processor import load_notebook, extract_page
            notebook = load_notebook(note_path)
            page_data = extract_page(notebook, page_num, ocr_pdf_layers=True)
            
            # Convert PNG bytes to PIL Image
            img = Image.open(io.BytesIO(page_data.png_bytes))
            actual_img_width, actual_img_height = img.size
            
            # Calculate PDF page size to fit image (maintain aspect ratio)
            # Supernote pages are typically 1404x1872 (portrait)
            pdf_width = 612  # 8.5 inches at 72 DPI
            pdf_height = int(pdf_width * actual_img_height / actual_img_width)
            
            # Set page size for this page
            c.setPageSize((pdf_width, pdf_height))
            
            # Draw the image (visible layer)
            img_reader = ImageReader(img)
            c.drawImage(img_reader, 0, 0, width=pdf_width, height=pdf_height)
            
            # Add invisible OCR text layer
            # Use text rendering mode 3 (invisible) for searchable but invisible text
            # This is the correct way to add OCR layer to PDFs
            
            if debug_mode:
                logger.info(f"=== DEBUG PAGE {page_num + 1} ===")
                logger.info(f"Image dimensions (stored): {img_width}x{img_height}")
                logger.info(f"Image dimensions (actual PIL): {actual_img_width}x{actual_img_height}")
                if actual_img_width != img_width or actual_img_height != img_height:
                    logger.warning(f"  ⚠️  MISMATCH! Stored vs actual dimensions differ!")
                logger.info(f"OCR image dimensions: {ocr_result.ocr_image_width}x{ocr_result.ocr_image_height}")
                logger.info(f"PDF dimensions: {pdf_width}x{pdf_height}")
                logger.info(f"Total blocks: {len(ocr_result.text_blocks)}")
            
            for idx, block in enumerate(ocr_result.text_blocks):
                text = block.text.strip()
                if not text:
                    continue
                
                # Convert bbox from OCR coordinates to PDF coordinates
                # bbox format: [left, top, right, bottom]
                # Qwen3-VL returns normalized coordinates (0-1000), Vision returns pixels
                # This needs to match the logic in note_processor.py for .note files
                left, top, right, bottom = block.bbox
                
                # CRITICAL FIX: Qwen3-VL returns normalized coordinates (0-1000), not pixels!
                # Convert from 0-1000 range to actual pixel coordinates
                if max(left, top, right, bottom) <= 1000:
                    # Qwen3-VL format: normalized coordinates (0-1000)
                    left_px = (left / 1000.0) * actual_img_width
                    top_px = (top / 1000.0) * actual_img_height
                    right_px = (right / 1000.0) * actual_img_width
                    bottom_px = (bottom / 1000.0) * actual_img_height
                else:
                    # Vision format: already in pixels
                    left_px = left
                    top_px = top
                    right_px = right
                    bottom_px = bottom
                
                # Now normalize by actual image dimensions to get fractions
                left_frac = left_px / actual_img_width
                top_frac = top_px / actual_img_height
                right_frac = right_px / actual_img_width
                bottom_frac = bottom_px / actual_img_height
                
                # Convert to PDF coordinates (in points)
                x = left_frac * pdf_width
                # PDF Y-axis starts from bottom, image from top
                y = pdf_height - (bottom_frac * pdf_height)
                bbox_width = (right_frac - left_frac) * pdf_width
                bbox_height = (bottom_frac - top_frac) * pdf_height
                
                # Debug logging for first 5 blocks
                if debug_mode and idx < 5:
                    logger.info(f"\nBlock {idx}: '{text[:30]}...'")
                    logger.info(f"  Raw bbox: [{left:.2f}, {top:.2f}, {right:.2f}, {bottom:.2f}]")
                    logger.info(f"  Fractions: [{left_frac:.4f}, {top_frac:.4f}, {right_frac:.4f}, {bottom_frac:.4f}]")
                    logger.info(f"  PDF coords: x={x:.1f}, y={y:.1f}, w={bbox_width:.1f}, h={bbox_height:.1f}")
                
                # In debug mode, draw visible rectangles around text
                if debug_mode:
                    c.setStrokeColorRGB(1, 0, 0)  # Red border
                    c.setLineWidth(0.5)
                    c.rect(x, y, bbox_width, bbox_height, stroke=1, fill=0)
                
                # Calculate font size to match bbox height
                # Font size should be approximately 80% of bbox height for proper fit
                # (text height includes ascenders/descenders, not just the bbox)
                font_size = bbox_height * 0.8
                
                # Clamp font size to reasonable range
                font_size = max(1, min(font_size, 100))
                
                # Text baseline should be at the bottom of the bbox
                # In PDF, y is already the bottom coordinate, so use it directly
                text_y = y
                
                if debug_mode:
                    c.setFillColorRGB(0, 0, 1)  # Blue text
                    logger.info(f"  Font size: {font_size:.1f}, text_y: {text_y:.1f}")
                else:
                    c.setFillColorRGB(0, 0, 0, alpha=0)  # Invisible
                
                c.setFont("Helvetica", font_size)
                
                # Draw text at adjusted position
                if debug_mode:
                    # Visible text in debug mode
                    c.drawString(x, text_y, text)
                else:
                    # Invisible text in production
                    text_obj = c.beginText(x, text_y)
                    text_obj.setTextRenderMode(3)  # Invisible
                    text_obj.textLine(text)
                    c.drawText(text_obj)
            
            # Finish page
            c.showPage()
        
        # Save PDF
        c.save()
        
        logger.info(f"Generated searchable PDF: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Failed to export PDF for {note_path}: {e}")
        return None


def export_note_to_pdf_simple(
    note_path: Path,
    page_images: Dict[int, bytes],
    page_ocr_text: Dict[int, str],
    supernote_data_path: Path,
    output_base_path: Path
) -> Optional[Path]:
    """
    Simplified PDF export with just text overlay (no bounding boxes).
    
    Args:
        note_path: Path to the .note file
        page_images: Dict mapping page_num to PNG image bytes
        page_ocr_text: Dict mapping page_num to full OCR text
        supernote_data_path: Base path of Supernote data directory
        output_base_path: Base path for PDF exports
        
    Returns:
        Path to the generated PDF, or None if export failed
    """
    try:
        # Calculate relative path
        rel_path = note_path.relative_to(supernote_data_path)
        output_path = output_base_path / rel_path.parent / f"{rel_path.stem}.pdf"
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create PDF
        c = canvas.Canvas(str(output_path), pagesize=letter)
        
        # Sort pages
        sorted_pages = sorted(page_images.items())
        
        for page_num, img_bytes in sorted_pages:
            # Load image
            img = Image.open(io.BytesIO(img_bytes))
            img_width, img_height = img.size
            
            # Calculate PDF page size
            pdf_width = 612
            pdf_height = int(pdf_width * img_height / img_width)
            c.setPageSize((pdf_width, pdf_height))
            
            # Draw image
            img_reader = ImageReader(img)
            c.drawImage(img_reader, 0, 0, width=pdf_width, height=pdf_height)
            
            # Add invisible text layer (simple overlay at bottom)
            if page_num in page_ocr_text:
                c.setFillColorRGB(1, 1, 1, alpha=0)
                c.setFont("Helvetica", 1)  # Tiny invisible font
                text_obj = c.beginText(0, 0)
                text_obj.textLines(page_ocr_text[page_num])
                c.drawText(text_obj)
            
            c.showPage()
        
        c.save()
        
        logger.info(f"Generated simple PDF: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Failed to export simple PDF for {note_path}: {e}")
        return None
