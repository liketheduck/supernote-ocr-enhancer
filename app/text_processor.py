"""
Text processing utilities with AI-powered cleanup and enhancement.

Provides functions for:
- Cleaning up OCR errors
- Improving text formatting
- Preserving document structure
"""

import logging
from typing import Optional

from ocr_client import OCRClient

logger = logging.getLogger(__name__)


def cleanup_ocr_text_with_ai(ocr_text: str, ocr_client: OCRClient) -> str:
    """
    Clean up OCR text using AI to fix errors while preserving structure.
    
    This function:
    - Fixes obvious OCR errors (character confusion, fragmented words)
    - Corrects punctuation and spacing
    - Preserves paragraph breaks and formatting
    - Does NOT change meaning or add content
    
    Args:
        ocr_text: Raw OCR text to clean up
        ocr_client: OCR client with access to Qwen model
        
    Returns:
        Cleaned up text with errors corrected
        
    Note:
        Falls back to original text if AI cleanup fails
    """
    if not ocr_text or not ocr_text.strip():
        return ocr_text
    
    # Limit text length to avoid timeout (max ~2000 chars for cleanup)
    text_to_clean = ocr_text[:2000] if len(ocr_text) > 2000 else ocr_text
    was_truncated = len(ocr_text) > 2000
    
    prompt = f"""You are an OCR text corrector. Your task is to clean and correct the following text while maintaining EXACTLY the original structure.

STRICT RULES:
1. Fix ONLY obvious OCR errors (e.g., "l0" → "lo", "rn" → "m")
2. Join fragmented words (e.g., "frag mented" → "fragmented")
3. Fix basic punctuation (spaces before periods, capitalization after periods)
4. PRESERVE all line breaks and paragraphs EXACTLY as they are
5. DO NOT change the meaning or content
6. DO NOT add explanations, comments, or new text
7. DO NOT translate or paraphrase
8. Return ONLY the corrected text, nothing else

OCR Text:
{text_to_clean}

Corrected text:"""
    
    try:
        logger.debug(f"Cleaning up OCR text ({len(text_to_clean)} chars)")
        cleaned = ocr_client.generate_text(prompt, max_tokens=len(text_to_clean.split()) * 2, temperature=0.1)
        
        # Basic validation: cleaned text shouldn't be drastically different in length
        if len(cleaned) < len(text_to_clean) * 0.5 or len(cleaned) > len(text_to_clean) * 2:
            logger.warning(f"AI cleanup produced suspicious length change: {len(text_to_clean)} → {len(cleaned)}, using original")
            return ocr_text
        
        # If text was truncated, append the remaining part
        if was_truncated:
            remaining = ocr_text[2000:]
            cleaned = cleaned + remaining
        
        logger.info(f"Successfully cleaned up OCR text")
        return cleaned.strip()
        
    except ValueError as e:
        # Model not loaded
        logger.debug(f"AI cleanup not available: {e}")
        return ocr_text
    except Exception as e:
        logger.warning(f"Failed to cleanup text with AI: {e}")
        return ocr_text


def generate_summary_with_ai(ocr_text: str, ocr_client: OCRClient, max_length: int = 200) -> Optional[str]:
    """
    Generate an intelligent summary of OCR text using AI.
    
    Args:
        ocr_text: Full OCR text to summarize
        ocr_client: OCR client with access to Qwen model
        max_length: Maximum length of summary in characters
        
    Returns:
        Generated summary, or None if generation fails
    """
    if not ocr_text or not ocr_text.strip():
        return None
    
    # Use first ~2000 chars for summary
    text_to_summarize = ocr_text[:2000] if len(ocr_text) > 2000 else ocr_text
    
    prompt = f"""Summarize the following text in 2-3 concise and clear sentences. The summary should capture the main ideas.

RULES:
- Maximum 2-3 sentences
- Be concise but informative
- Capture the main ideas
- DO NOT add information that is not in the text
- Write in the same language as the original text

Text:
{text_to_summarize}

Summary:"""
    
    try:
        logger.debug(f"Generating summary for {len(text_to_summarize)} chars of text")
        summary = ocr_client.generate_text(prompt, max_tokens=150, temperature=0.3)
        
        # Truncate if too long
        if len(summary) > max_length:
            # Try to cut at sentence boundary
            sentences = summary.split('. ')
            summary = '. '.join(sentences[:2])
            if not summary.endswith('.'):
                summary += '.'
        
        logger.info(f"Successfully generated summary ({len(summary)} chars)")
        return summary.strip()
        
    except ValueError as e:
        # Model not loaded
        logger.debug(f"AI summary not available: {e}")
        return None
    except Exception as e:
        logger.warning(f"Failed to generate summary with AI: {e}")
        return None
