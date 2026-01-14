"""
Logseq export functionality for Supernote notes.

Generates Logseq markdown pages with:
- Link to PDF in assets
- Metadata (date, source, OCR confidence)
- Auto-generated tags
- Optional summary (for multi-page notes)
- Full OCR text content
"""

import logging
import json
from pathlib import Path
from typing import Dict, Tuple, Optional
from datetime import datetime
import re

from ocr_client import OCRResult

logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """Sanitize filename for filesystem compatibility."""
    # Remove or replace problematic characters
    name = re.sub(r'[<>:"/\\|?*]', '-', name)
    # Remove leading/trailing spaces and dots
    name = name.strip('. ')
    return name


def build_flat_filename_from_path(rel_path: Path) -> str:
    """
    Generate a flat filename from a relative path, avoiding conflicts.
    
    Examples:
    - Path('nota.md') -> 'nota.md'
    - Path('ProyectoA/Cliente1/nota1.md') -> 'ProyectoA_Cliente1_nota1.md'
    - Path('AreaX/SubareaY/notaZ.md') -> 'AreaX_SubareaY_notaZ.md'
    
    Args:
        rel_path: Relative path from supernote_export/
        
    Returns:
        Flat filename with path segments joined by underscores
    """
    if len(rel_path.parts) <= 1:
        # Root level file, keep original name
        return rel_path.name
    
    # Join parent directories with underscore, then add filename
    parent_segments = '_'.join(rel_path.parts[:-1])
    filename = rel_path.name
    return f"{parent_segments}_{filename}"


def build_page_properties_from_path(rel_path: Path) -> dict:
    """
    Generate Logseq page properties from a relative path.
    
    Examples:
    - Path('nota.md') -> {'source': 'Supernote', 'path': 'Supernote', 'tags': ['[[Supernote]]']}
    - Path('ProyectoA/Cliente1/nota1.md') -> {
        'source': 'Supernote',
        'path': 'Supernote/ProyectoA/Cliente1',
        'tags': ['[[Supernote]]', '[[Supernote/ProyectoA]]', '[[Supernote/ProyectoA/Cliente1]]']
      }
    
    Args:
        rel_path: Relative path from supernote_export/
        
    Returns:
        Dictionary with source, path, and tags properties
    """
    # Remove file extension to get folder path
    if len(rel_path.parts) <= 1:
        # Root level file
        path_segments = []
    else:
        path_segments = list(rel_path.parts[:-1])  # All parts except filename
    
    # Build path property
    path_property = "Supernote"
    if path_segments:
        path_property += "/" + "/".join(path_segments)
    
    # Build cumulative tags
    tags = ["[[Supernote]]"]
    cumulative_path = "Supernote"
    for segment in path_segments:
        cumulative_path += "/" + segment
        tags.append(f"[[{cumulative_path}]]")
    
    return {
        'source': 'Supernote',
        'path': path_property,
        'tags': tags
    }


def merge_properties_with_content(content: str, properties: dict) -> str:
    """
    Merge properties into the first property block of Logseq content.
    
    If no property block exists, creates one at the beginning.
    Preserves existing properties and adds/updates source, path, tags.
    
    Args:
        content: Existing markdown content
        properties: Dictionary of properties to add/update
        
    Returns:
        Content with merged properties
    """
    lines = content.split('\n')
    property_start = -1
    property_end = -1
    existing_properties = {}
    
    # Find existing property block (lines with "key:: value" pattern)
    for i, line in enumerate(lines):
        if '::' in line and line.strip():
            if property_start == -1:
                property_start = i
            # Parse existing property
            key, value = line.split('::', 1)
            existing_properties[key.strip()] = value.strip()
            property_end = i + 1  # Update end as we find properties
        elif property_start != -1 and line.strip() and '::' not in line:
            # Property block ended
            break
        elif property_start != -1 and not line.strip():
            # Empty line within property block - continue
            continue
        else:
            # No property block yet, continue
            continue
    
    # Merge properties (new ones override existing)
    merged_properties = {**existing_properties, **properties}
    
    # Build property block
    property_lines = []
    for key, value in merged_properties.items():
        if key == 'tags' and isinstance(value, list):
            # Tags as comma-separated list
            property_lines.append(f"{key}:: {', '.join(value)}")
        else:
            property_lines.append(f"{key}:: {value}")
    
    # Rebuild content
    if property_start >= 0:
        # Replace existing property block
        before = lines[:property_start]
        after = lines[property_end:]
        
        return '\n'.join(before + property_lines + [''] + after)
    else:
        # Add property block at beginning
        return '\n'.join(property_lines + [''] + lines)


def calculate_average_confidence(page_results: Dict[int, Tuple[OCRResult, int, int]]) -> float:
    """Calculate average OCR confidence across all pages."""
    total_confidence = 0.0
    total_blocks = 0
    
    for ocr_result, _, _ in page_results.values():
        for block in ocr_result.text_blocks:
            if hasattr(block, 'confidence') and block.confidence is not None:
                total_confidence += block.confidence
                total_blocks += 1
    
    if total_blocks == 0:
        return 0.0
    
    return (total_confidence / total_blocks) * 100


def generate_tags(note_path: Path, ocr_text: str) -> list[str]:
    """
    Generate relevant tags for the note.
    
    Currently uses simple heuristics based on path and content.
    Future: Could use LLM for smarter tag generation.
    """
    tags = ["supernote"]
    
    # Add tags based on folder structure
    parts = note_path.parts
    for part in parts:
        part_lower = part.lower()
        # Skip common/generic folder names
        if part_lower in ['note', 'document', 'user', 'supernote']:
            continue
        # Add folder name as tag
        tag = re.sub(r'[^a-z0-9]+', '-', part_lower).strip('-')
        if tag and len(tag) > 2:
            tags.append(tag)
    
    # Simple keyword detection (can be enhanced with LLM)
    text_lower = ocr_text.lower()
    
    # Common categories
    if any(word in text_lower for word in ['meeting', 'agenda', 'minutes']):
        tags.append('meeting')
    if any(word in text_lower for word in ['todo', 'task', 'action item']):
        tags.append('tasks')
    if any(word in text_lower for word in ['idea', 'brainstorm', 'concept']):
        tags.append('ideas')
    if any(word in text_lower for word in ['project', 'plan', 'roadmap']):
        tags.append('project')
    
    # Remove duplicates while preserving order
    seen = set()
    unique_tags = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            unique_tags.append(tag)
    
    return unique_tags


def generate_summary(ocr_text: str, max_length: int = 200) -> str:
    """
    Generate a summary of the note content.
    
    Currently uses simple extraction of first few sentences.
    Future: Could use LLM for better summarization.
    """
    # Clean up text
    text = ocr_text.strip()
    
    # Split into sentences (simple approach)
    sentences = re.split(r'[.!?]+', text)
    
    # Take first 2-3 sentences
    summary_parts = []
    current_length = 0
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        if current_length + len(sentence) > max_length:
            break
        
        summary_parts.append(sentence)
        current_length += len(sentence)
        
        if len(summary_parts) >= 3:
            break
    
    summary = '. '.join(summary_parts)
    if summary and not summary.endswith('.'):
        summary += '.'
    
    return summary or "No summary available."


def format_logseq_date(date: datetime) -> str:
    """Format date as Logseq journal link."""
    # Logseq format: [[Jan 13th, 2026]]
    day = date.day
    suffix = 'th' if 11 <= day <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
    return f"[[{date.strftime('%b')} {day}{suffix}, {date.year}]]"


def format_text_for_logseq(text: str, indent: str = "    ") -> list[str]:
    """
    Format OCR text for Logseq, preserving paragraphs.
    
    Rules:
    - Blank lines (double newline) separate paragraphs
    - Lines within a paragraph are joined together
    - Each paragraph becomes one bullet point
    
    Args:
        text: OCR text to format
        indent: Indentation string for bullets
        
    Returns:
        List of formatted lines for Logseq
    """
    lines = []
    
    # Split by double newlines (paragraph breaks)
    paragraphs = text.split('\n\n')
    
    for para in paragraphs:
        if not para.strip():
            continue
        
        # Join lines within paragraph, preserving single spaces
        para_lines = [line.strip() for line in para.split('\n') if line.strip()]
        para_text = ' '.join(para_lines)
        
        if para_text:
            lines.append(f"{indent}- {para_text}")
    
    # If no paragraphs were detected (no double newlines), treat as single paragraph
    if not lines and text.strip():
        text_lines = [line.strip() for line in text.split('\n') if line.strip()]
        text_joined = ' '.join(text_lines)
        lines.append(f"{indent}- {text_joined}")
    
    return lines


def export_note_to_logseq_flat(
    note_path: Path,
    page_results: Dict[int, Tuple[OCRResult, int, int]],
    supernote_data_path: Path,
    logseq_pages_path: Path,
    logseq_assets_path: Path,
    pdf_source_path: Optional[Path] = None,
    ocr_client: Optional['OCRClient'] = None
) -> Optional[Path]:
    """
    Export a Supernote .note file to Logseq markdown format with flat structure.
    
    This version creates a flat file structure in pages/ and preserves hierarchy
    in page properties (source, path, tags).
    
    Args:
        note_path: Path to the .note file
        page_results: Dict mapping page_num to (OCRResult, width, height)
        supernote_data_path: Base path of Supernote data directory
        logseq_pages_path: Base path for Logseq pages (e.g., ~/logseq/pages)
        logseq_assets_path: Base path for Logseq assets (e.g., ~/logseq/assets)
        pdf_source_path: Optional path to existing PDF to copy (if None, assumes PDF export is separate)
        ocr_client: Optional OCR client for AI summaries
        
    Returns:
        Path to the generated markdown file, or None if export failed
    """
    try:
        # Calculate relative path from supernote data directory
        rel_path = note_path.relative_to(supernote_data_path)
        
        # Generate flat filename and properties
        flat_filename = build_flat_filename_from_path(rel_path)
        page_properties = build_page_properties_from_path(rel_path)
        
        # Output paths - flat structure
        md_output_path = logseq_pages_path / flat_filename
        pdf_asset_path = logseq_assets_path / "supernote" / flat_filename.replace('.md', '.pdf')
        
        # Ensure output directories exist (flat structure)
        logseq_pages_path.mkdir(parents=True, exist_ok=True)
        pdf_asset_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy or generate PDF for Logseq assets
        if pdf_source_path and pdf_source_path.exists():
            # PDF already generated by OCR_PDF_EXPORT, just copy it
            import shutil
            shutil.copy2(pdf_source_path, pdf_asset_path)
            logger.debug(f"Copied PDF to Logseq assets: {pdf_asset_path}")
        else:
            # Generate PDF directly for Logseq (if PDF export is disabled)
            logger.debug(f"Generating PDF for Logseq assets: {pdf_asset_path}")
            from pdf_exporter import export_note_to_pdf
            
            # Generate PDF directly to Logseq assets
            temp_pdf = export_note_to_pdf(
                note_path,
                page_results,
                supernote_data_path,
                logseq_assets_path / "supernote"
            )
            if not temp_pdf:
                logger.warning(f"Failed to generate PDF for Logseq: {note_path}")
                # Continue anyway - markdown will be created with broken PDF link
        
        # Collect all OCR text
        sorted_pages = sorted(page_results.items())
        page_texts = []
        for page_num, (ocr_result, _, _) in sorted_pages:
            page_texts.append(ocr_result.full_text)
        
        full_text = '\n\n'.join(page_texts)
        
        # Calculate metadata
        avg_confidence = calculate_average_confidence(page_results)
        num_pages = len(page_results)
        word_count = len(full_text.split())
        
        # Generate additional tags from content (keep existing function)
        content_tags = generate_tags(rel_path, full_text)
        
        # Generate summary if multi-page
        summary = None
        if num_pages > 3:
            # Try AI summary first if ocr_client available
            if ocr_client:
                from text_processor import generate_summary_with_ai
                summary = generate_summary_with_ai(full_text, ocr_client)
            
            # Fallback to simple summary if AI fails or not available
            if not summary:
                summary = generate_summary(full_text)
        
        # Build Logseq markdown content
        lines = []
        
        # PDF link with metadata (using image syntax for proper PDF embedding)
        pdf_rel_path = f"../assets/supernote/{flat_filename.replace('.md', '.pdf')}"
        pdf_name = Path(flat_filename).stem
        lines.append(f"![{pdf_name}]({pdf_rel_path})")
        
        # Metadata as bullet points
        processing_date = format_logseq_date(datetime.now())
        lines.append(f"  - **Fecha procesamiento**: {processing_date}")
        lines.append(f"  - **Confianza OCR**: {avg_confidence:.1f}%")
        lines.append(f"  - **Páginas**: {num_pages}")
        lines.append(f"  - **Palabras**: {word_count}")
        
        # Additional tags from content
        if content_tags:
            tag_str = ' '.join(f'#{tag}' for tag in content_tags)
            lines.append(f"  - **Tags contenido**: {tag_str}")
        
        # Summary section (if multi-page)
        if summary:
            lines.append("- ## Resumen")
            lines.append(f"  - {summary}")
        
        # Content section
        lines.append("- ## Contenido")
        
        # Add page markers for multi-page notes
        if num_pages > 1:
            for page_num, (ocr_result, _, _) in sorted_pages:
                lines.append(f"  - ### Página {page_num + 1}")
                # Format text preserving paragraphs
                formatted_lines = format_text_for_logseq(ocr_result.full_text, indent="    ")
                lines.extend(formatted_lines)
        else:
            # Single page - format text preserving paragraphs
            formatted_lines = format_text_for_logseq(full_text, indent="  ")
            lines.extend(formatted_lines)
        
        # Build final content with properties
        md_content = '\n'.join(lines)
        
        # Merge page properties at the beginning
        final_content = merge_properties_with_content(md_content, page_properties)
        
        # Write markdown file
        md_output_path.write_text(final_content, encoding='utf-8')
        
        logger.info(f"Generated Logseq page (flat structure): {md_output_path}")
        logger.debug(f"  - Flat filename: {flat_filename}")
        logger.debug(f"  - Properties: source={page_properties['source']}, path={page_properties['path']}")
        logger.debug(f"  - Tags: {', '.join(page_properties['tags'])}")
        
        return md_output_path
        
    except Exception as e:
        logger.error(f"Failed to export Logseq page for {note_path}: {e}")
        return None


# Keep the original function for backwards compatibility
def export_note_to_logseq(
    note_path: Path,
    page_results: Dict[int, Tuple[OCRResult, int, int]],
    supernote_data_path: Path,
    logseq_pages_path: Path,
    logseq_assets_path: Path,
    pdf_source_path: Optional[Path] = None,
    ocr_client: Optional['OCRClient'] = None
) -> Optional[Path]:
    """
    Legacy wrapper for backwards compatibility.
    
    This function maintains the old hierarchical structure.
    For new implementations, use export_note_to_logseq_flat() instead.
    """
    # Import the original implementation if needed, or redirect to flat version
    # For now, redirect to flat version as it's the preferred approach
    return export_note_to_logseq_flat(
        note_path=note_path,
        page_results=page_results,
        supernote_data_path=supernote_data_path,
        logseq_pages_path=logseq_pages_path,
        logseq_assets_path=logseq_assets_path,
        pdf_source_path=pdf_source_path,
        ocr_client=ocr_client
    )
