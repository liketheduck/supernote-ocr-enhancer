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
from typing import Dict, Tuple, Optional, List
from datetime import datetime
import re

from ocr_client import OCRResult
from metadata_analyzer import MetadataAnalyzer

logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """Sanitize filename for filesystem compatibility."""
    # Remove or replace problematic characters
    name = re.sub(r'[<>:"/\\|?*]', '-', name)
    # Remove leading/trailing spaces and dots
    name = name.strip('. ')
    return name


def clean_note_title(filename: str) -> str:
    """
    Clean note title by removing date prefix and 'Note_' prefix.
    
    Examples:
    - "Note_20251230_Comidas semana Navidades.note" -> "Comidas semana Navidades"
    - "20251230_Comidas semana Navidades.note" -> "Comidas semana Navidades"
    - "Note_Meeting notes.note" -> "Meeting notes"
    
    Args:
        filename: Original filename with extension
        
    Returns:
        Clean title without date and prefixes
    """
    # Remove extension
    name_without_ext = Path(filename).stem
    
    # Remove date prefix (YYYYMMDD_)
    date_pattern = r'^\d{8}_'
    name_without_date = re.sub(date_pattern, '', name_without_ext)
    
    # Remove 'Note_' prefix
    note_pattern = r'^Note_'
    clean_title = re.sub(note_pattern, '', name_without_date)
    
    # If nothing left after removing prefixes, use original without extension
    if not clean_title.strip():
        clean_title = name_without_ext
    
    return clean_title.strip()


def clean_page_title(title: str) -> str:
    """
    Clean page title by removing 'Note_' prefix and date prefixes.
    
    Examples:
    - "Note_20251230_Comidas semana Navidades" -> "Comidas semana Navidades"
    - "20251230_Comidas semana Navidades" -> "Comidas semana Navidades"
    - "Note_Meeting notes" -> "Meeting notes"
    
    Args:
        title: Original page title
        
    Returns:
        Clean title without date and prefixes
    """
    # Remove date prefix (YYYYMMDD_)
    date_pattern = r'^\d{8}_'
    name_without_date = re.sub(date_pattern, '', title)
    
    # Remove 'Note_' prefix
    note_pattern = r'^Note_'
    clean_title = re.sub(note_pattern, '', name_without_date)
    
    # If nothing left after removing prefixes, use original
    if not clean_title.strip():
        clean_title = title
    
    return clean_title.strip()


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


def build_enhanced_frontmatter(note_date: Optional[str], 
                               metadata, 
                               enhanced_tags: List[str], 
                               ocr_confidence: float,
                               num_pages: int,
                               word_count: int) -> str:
    """
    Build enhanced front matter with AI-powered metadata.
    
    Args:
        note_date: Extracted date from filename/content
        metadata: NoteMetadata from analysis
        enhanced_tags: Generated enhanced tags
        ocr_confidence: OCR confidence score
        num_pages: Number of pages in the note
        word_count: Word count of the note
        
    Returns:
        Front matter string with Logseq property format
    """
    properties = []
    
    # Core metadata
    properties.append("source:: [[Supernote]]")
    properties.append(f"path:: Supernote/{metadata.content_type}")
    
    if note_date:
        properties.append(f"date:: {note_date}")
    
    # Use Logseq date format
    processed_date = datetime.now().strftime('%b %dth, %Y')
    properties.append(f"processed:: [[{processed_date}]]")
    properties.append(f"ocr-confidence:: {ocr_confidence:.1f}%")
    
    # Additional metadata
    properties.append(f"pages:: {num_pages}")
    properties.append(f"words:: {word_count}")
    
    # IA analysis
    properties.append(f"language:: {metadata.language}")
    properties.append(f"type:: [[Supernote/{metadata.content_type}]]")
    
    # Enhanced tags
    tags_str = ", ".join(enhanced_tags)
    properties.append(f"tags:: {tags_str}")
    
    return "\n".join(properties)


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


def format_content_for_logseq_outline(page_results: Dict[int, Tuple[OCRResult, int, int]], note_title: str = None) -> List[str]:
    """
    Format OCR content in native Logseq outline structure with page headers.
    
    Args:
        page_results: Dict mapping page_num to (OCRResult, width, height)
        note_title: Optional note title to use in page headers
        
    Returns:
        List of formatted lines for Logseq outline structure
    """
    lines = []
    
    # Sort pages by page number
    sorted_pages = sorted(page_results.items())
    total_pages = len(sorted_pages)
    
    # Clean note title if provided
    clean_title = clean_page_title(note_title) if note_title else None
    
    for page_num, (ocr_result, _, _) in sorted_pages:
        # Add page header with clean title if available
        if clean_title and total_pages == 1:
            # Single page - use title as header
            page_header = clean_title
        else:
            # Multiple pages - use page number
            page_header = f"Página {page_num}/{total_pages}"
        
        lines.append(f"  - {page_header}")
        
        # Get page text
        page_text = ocr_result.full_text.strip()
        
        if page_text:
            # Split by paragraphs (double newlines)
            paragraphs = page_text.split('\n\n')
            
            for para in paragraphs:
                if not para.strip():
                    continue
                
                # Clean up paragraph text
                para_lines = [line.strip() for line in para.split('\n') if line.strip()]
                para_text = ' '.join(para_lines)
                
                if para_text:
                    # Add as child element with proper indentation
                    lines.append(f"    - {para_text}")
        
        # Add empty line between pages for readability
        if page_num < total_pages:
            lines.append("")
    
    return lines


def format_text_for_logseq(text: str, indent: str) -> List[str]:
    """
    Format OCR text for Logseq with proper indentation.
    
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
        
        # Generate flat filename and clean it
        flat_filename = build_flat_filename_from_path(rel_path)
        # Remove .note extension first, then clean, then add .md
        flat_filename_no_ext = flat_filename.replace('.note', '')
        flat_filename = clean_page_title(flat_filename_no_ext) + '.md'
        
        # Collect all OCR text for analysis
        sorted_pages = sorted(page_results.items())
        page_texts = []
        for page_num, (ocr_result, _, _) in sorted_pages:
            page_texts.append(ocr_result.full_text)
        
        full_text = '\n\n'.join(page_texts)
        
        # AI-powered metadata analysis
        analyzer = MetadataAnalyzer(ocr_client)
        note_date = analyzer.extract_note_date(note_path.name, full_text)
        metadata, enhanced_tags = analyzer.analyze_note(full_text, note_path.name, use_ai=bool(ocr_client))
        
        logger.info(f"  🤖 Analysis: type={metadata.content_type}, tags={len(enhanced_tags)}, date={note_date}")
        logger.info(f"  🏷️  Enhanced tags: {', '.join(enhanced_tags[:3])}{'...' if len(enhanced_tags) > 3 else ''}")
        
        # Calculate metadata
        avg_confidence = calculate_average_confidence(page_results)
        
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
            logger.info(f"📄 Logseq PDF - Source: {pdf_source_path}")
            logger.info(f"📄 Logseq PDF - Asset: {pdf_asset_path}")
            logger.info(f"📄 Logseq PDF - Source exists: {pdf_source_path.exists()}")
            if pdf_source_path.exists():
                file_size = pdf_source_path.stat().st_size
                logger.info(f"📄 Logseq PDF - Source size: {file_size} bytes")
                shutil.copy2(pdf_source_path, pdf_asset_path)
                logger.info(f"📄 Logseq PDF - Copied successfully")
                logger.info(f"📄 Logseq PDF - Asset exists: {pdf_asset_path.exists()}")
            else:
                logger.warning(f"📄 Logseq PDF - Source path does not exist: {pdf_source_path}")
        else:
            logger.warning(f"📄 Logseq PDF - No PDF source path available: {pdf_source_path}")
            # Generate PDF directly for Logseq (if PDF export is disabled)
            logger.info(f"📄 Logseq PDF - Generating PDF for assets: {pdf_asset_path}")
            from pdf_exporter import export_note_to_pdf
            
            # Generate PDF directly to Logseq assets
            # Create a temporary directory for PDF generation
            import tempfile
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_pdf = export_note_to_pdf(
                    note_path,
                    page_results,
                    supernote_data_path,
                    Path(temp_dir)
                )
                if temp_pdf and temp_pdf.exists():
                    # Copy the generated PDF to the final location
                    import shutil
                    shutil.copy2(temp_pdf, pdf_asset_path)
                    logger.info(f"📄 Logseq PDF - Generated and copied successfully: {pdf_asset_path}")
                else:
                    logger.warning(f"📄 Logseq PDF - Failed to generate PDF: {note_path}")
                    # Continue anyway - markdown will be created with broken PDF link
        
        # Calculate remaining metadata
        num_pages = len(page_results)
        word_count = len(full_text.split())
        
        # Generate summary if multi-page (keep existing logic)
        summary = None
        if num_pages > 3:
            # Try AI summary first if ocr_client available
            if ocr_client:
                from text_processor import generate_summary_with_ai
                summary = generate_summary_with_ai(full_text, ocr_client)
            
            # Fallback to simple summary if AI fails or not available
            if not summary:
                summary = generate_summary(full_text)
        
        # Build enhanced front matter
        enhanced_frontmatter = build_enhanced_frontmatter(
            note_date=note_date,
            metadata=metadata,
            enhanced_tags=enhanced_tags,
            ocr_confidence=avg_confidence,
            num_pages=num_pages,
            word_count=word_count
        )
        
        # Build Logseq markdown content
        lines = []
        
        # PDF link with clean title (using image syntax for proper PDF embedding)
        clean_title = clean_note_title(note_path.name)
        pdf_filename = flat_filename.replace('.md', '.pdf')
        pdf_rel_path = f"../assets/supernote/{pdf_filename}"
        lines.append(f"![{clean_title}]({pdf_rel_path})")
        
        lines.append("")
        
        # Add summary if generated
        if summary:
            lines.append("- ## Resumen generado")
            lines.append(f"  - {summary}")
            lines.append("")
        
        # Add content with outline structure
        lines.append("- ## Contenido")
        
        # Format content in native Logseq outline structure
        outline_content = format_content_for_logseq_outline(page_results, note_path.name)
        lines.extend(outline_content)
        
        # Write markdown file with enhanced front matter
        content_lines = [enhanced_frontmatter, ''] + lines
        content = '\n'.join(content_lines)
        
        # Write markdown file
        md_output_path.write_text(content, encoding='utf-8')
        
        logger.info(f"Generated Logseq page (enhanced): {md_output_path}")
        logger.debug(f"  - Flat filename: {flat_filename}")
        logger.debug(f"  - Content type: {metadata.content_type}")
        logger.debug(f"  - Enhanced tags: {', '.join(enhanced_tags[:3])}{'...' if len(enhanced_tags) > 3 else ''}")
        
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
