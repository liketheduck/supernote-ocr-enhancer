#!/usr/bin/env python3
"""
Supernote OCR Enhancer

Processes Supernote .note files by:
1. Scanning for .note files in the Supernote data directory
2. Extracting page images from .note files
3. Sending images to the MLX-VLM OCR API for high-quality handwriting recognition
4. Injecting the enhanced OCR data back into the .note files

Goal: Replace Supernote's ~27% word error rate OCR with ~5% error rate from Qwen2.5-VL.
"""

import os
import sys
import json
import logging
import time
import threading
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple
from datetime import datetime

from fastapi import FastAPI
import uvicorn

from database import Database, compute_file_hash, compute_image_hash
from ocr_client import OCRClient, OCRResult
from note_processor import (
    load_notebook,
    get_notebook_info,
    extract_page,
    inject_ocr_results,
    get_existing_ocr_text,
    has_ocr_data,
    export_ocr_text_to_file
)
from pdf_exporter import export_note_to_pdf
from logseq_exporter import export_note_to_logseq
from sync_handlers import create_sync_handler

# Configuration from environment
# Use localhost as default for native macOS execution; Docker users override via env
OCR_API_URL = os.getenv("OCR_API_URL", "http://localhost:8100")
SUPERNOTE_DATA_PATH = os.getenv("SUPERNOTE_DATA_PATH", "/supernote/data")
PROCESS_INTERVAL = int(os.getenv("PROCESS_INTERVAL", "0"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
CREATE_BACKUPS = os.getenv("CREATE_BACKUPS", "true").lower() == "true"
WRITE_TO_NOTE = os.getenv("WRITE_TO_NOTE", "true").lower() == "true"
RESET_DATABASE = os.getenv("RESET_DATABASE", "false").lower() == "true"
# Sync database configuration
STORAGE_MODE = os.getenv("STORAGE_MODE", "")
MACAPP_DATABASE_PATH = os.getenv("MACAPP_DATABASE_PATH", "")
MACAPP_NOTES_PATH = os.getenv("MACAPP_NOTES_PATH", "")
# FILE_RECOGN_TYPE: "0" = no device OCR, "1" = device OCR enabled, "keep" = preserve existing
FILE_RECOGN_TYPE = os.getenv("FILE_RECOGN_TYPE", "keep")
# OCR_PDF_LAYERS: Extract and OCR embedded PNGs from PDF/custom background layers
OCR_PDF_LAYERS = os.getenv("OCR_PDF_LAYERS", "true").lower() == "true"
# Skip the recently-uploaded check (for 3am full processing run)
SKIP_RECENT_CHECK = os.getenv("SKIP_RECENT_CHECK", "false").lower() == "true"
SYNC_SERVER_COMPOSE = os.getenv("SYNC_SERVER_COMPOSE", "")
SYNC_SERVER_ENV = os.getenv("SYNC_SERVER_ENV", "")
# Text export settings: save OCR text to local .txt files
OCR_TXT_EXPORT_ENABLED = os.getenv("OCR_TXT_EXPORT_ENABLED", "false").lower() == "true"
OCR_TXT_EXPORT_PATH = os.getenv("OCR_TXT_EXPORT_PATH", "")
# PDF export settings: generate searchable PDFs with embedded OCR
OCR_PDF_EXPORT_ENABLED = os.getenv("OCR_PDF_EXPORT_ENABLED", "false").lower() == "true"
OCR_PDF_EXPORT_PATH = os.getenv("OCR_PDF_EXPORT_PATH", "")
# Logseq export settings: generate Logseq markdown pages with PDF links
LOGSEQ_EXPORT_ENABLED = os.getenv("LOGSEQ_EXPORT_ENABLED", "false").lower() == "true"
LOGSEQ_PAGES_PATH = os.getenv("LOGSEQ_PAGES_PATH", "")
LOGSEQ_ASSETS_PATH = os.getenv("LOGSEQ_ASSETS_PATH", "")
# AI text processing: cleanup OCR errors with Qwen
AI_TEXT_CLEANUP_ENABLED = os.getenv("AI_TEXT_CLEANUP_ENABLED", "false").lower() == "true"
# PDF debug mode: visualize bounding boxes
PDF_DEBUG_MODE = os.getenv("PDF_DEBUG_MODE", "false").lower() == "true"

# Data path: supports both Docker (/app/data) and native execution
# For native: set DATA_PATH env var or it defaults to ./data relative to repo
def _resolve_data_path() -> Path:
    """Resolve data path for both Docker and native execution."""
    env_path = os.getenv("DATA_PATH")
    if env_path:
        return Path(env_path).expanduser()
    # Check if running in Docker (default path exists)
    docker_path = Path("/app/data")
    if docker_path.exists():
        return docker_path
    # Native execution: use ./data relative to this file's parent (repo root)
    return Path(__file__).parent.parent / "data"

DATA_PATH = _resolve_data_path()
BACKUP_PATH = DATA_PATH / "backups"
DB_PATH = DATA_PATH / "processing.db"

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("supernote-ocr-enhancer")

# Initialize components
db: Optional[Database] = None
ocr_client: Optional[OCRClient] = None
sync_handler = None  # Initialized in main()

# FastAPI app for health checks
app = FastAPI(title="Supernote OCR Enhancer")

# Track processing state
processing_state = {
    "status": "idle",
    "last_run": None,
    "files_processed": 0,
    "pages_processed": 0,
    "current_file": None,
    "errors": []
}


@dataclass
class ProcessingResult:
    """Result of processing a single .note file."""
    file_path: Path
    success: bool
    pages_processed: int
    pages_skipped: int
    total_time_ms: float
    error: Optional[str] = None


@app.get("/health")
async def health():
    """Health check endpoint"""
    ocr_available = ocr_client.health_check() if ocr_client else False
    return {
        "status": "healthy" if ocr_available else "degraded",
        "ocr_api_available": ocr_available,
        "processing_state": processing_state
    }


@app.get("/status")
async def status():
    """Detailed status endpoint"""
    stats = db.get_statistics() if db else {}
    return {
        "ocr_api_url": OCR_API_URL,
        "supernote_data_path": SUPERNOTE_DATA_PATH,
        "process_interval": PROCESS_INTERVAL,
        "write_to_note": WRITE_TO_NOTE,
        "processing_state": processing_state,
        "database_stats": stats,
        "note_files_found": count_note_files()
    }


@app.get("/stats")
async def stats():
    """Get processing statistics."""
    return db.get_statistics() if db else {}


def count_note_files() -> int:
    """Count .note files in Supernote data directory"""
    try:
        data_path = Path(SUPERNOTE_DATA_PATH)
        if not data_path.exists():
            return 0
        return len(list(data_path.rglob("*.note")))
    except Exception:
        return -1


def find_note_files() -> List[Path]:
    """Find all .note files in Supernote data directory"""
    data_path = Path(SUPERNOTE_DATA_PATH)
    if not data_path.exists():
        logger.warning(f"Supernote data path does not exist: {SUPERNOTE_DATA_PATH}")
        return []
    return list(data_path.rglob("*.note"))


def process_note_file(note_path: Path) -> ProcessingResult:
    """
    Process a single .note file.

    1. Check if processing is needed (based on file hash)
    2. Extract pages as PNG images
    3. Send each page to OCR API
    4. Store results in database
    5. Optionally inject OCR data back into .note file
    """
    global processing_state
    start_time = time.time()
    processing_state["current_file"] = str(note_path)

    try:
        # Compute file hash
        file_hash = compute_file_hash(note_path)
        file_stat = note_path.stat()

        # Check if processing needed
        should_process, reason = db.should_process_file(note_path, file_hash)
        if not should_process:
            # For "already_processed" files, verify all pages actually have OCR data
            # Pages can lose OCR due to sync conflicts or injection failures
            # Use has_ocr_data (not get_existing_ocr_text) to include empty OCR results
            if reason == "already_processed":
                notebook = load_notebook(note_path)
                pages_missing_ocr = []
                for i in range(len(notebook.pages)):
                    if not has_ocr_data(notebook, i):
                        pages_missing_ocr.append(i)
                if pages_missing_ocr:
                    should_process = True
                    reason = f"missing_ocr_pages:{pages_missing_ocr}"
                    logger.info(f"Processing {note_path.name} (reason: {reason})")
                else:
                    logger.info(f"Skipping {note_path.name}: {reason}")
                    return ProcessingResult(
                        file_path=note_path,
                        success=True,
                        pages_processed=0,
                        pages_skipped=0,
                        total_time_ms=0
                    )
            else:
                logger.info(f"Skipping {note_path.name}: {reason}")
                return ProcessingResult(
                    file_path=note_path,
                    success=True,
                    pages_processed=0,
                    pages_skipped=0,
                    total_time_ms=0
                )
        else:
            logger.info(f"Processing {note_path.name} (reason: {reason})")
            notebook = None  # Will be loaded below

        # Load notebook (if not already loaded during OCR verification)
        if notebook is None:
            notebook = load_notebook(note_path)
        total_pages = len(notebook.pages)

        # Update database
        note_id = db.upsert_note_file(
            note_path,
            file_hash,
            file_stat.st_mtime,
            file_stat.st_size,
            total_pages
        )
        db.update_status(note_path, 'processing')

        # Process each page
        pages_processed = 0
        pages_skipped = 0
        pages_failed = 0
        page_results: Dict[int, Tuple[OCRResult, int, int]] = {}

        for page_num in range(total_pages):
            try:
                # Extract page image
                page_data = extract_page(notebook, page_num, ocr_pdf_layers=OCR_PDF_LAYERS)
                page_hash = compute_image_hash(page_data.png_bytes)

                # Check if page needs OCR
                # Use has_ocr_data to check for ANY OCR data (including empty results)
                page_has_ocr = has_ocr_data(notebook, page_num)
                hash_matches = db.is_page_processed(note_id, page_num, page_hash)

                if hash_matches and page_has_ocr:
                    # Page unchanged and has OCR data - skip
                    logger.debug(f"  Page {page_num} unchanged with OCR, skipping")
                    pages_skipped += 1
                    continue
                elif hash_matches and not page_has_ocr:
                    # Page unchanged but OCR data missing (sync conflict?) - re-OCR
                    logger.info(f"  Page {page_num}: hash matches but OCR missing, re-processing")
                elif page_data.from_bglayer and page_has_ocr:
                    # PDF layer with existing OCR data from external source - preserve it
                    logger.info(f"  Page {page_num}: PDF layer already has OCR, skipping")
                    pages_skipped += 1
                    continue

                # Run OCR with Qwen2.5-VL (slower but more accurate)
                logger.info(f"  OCR page {page_num + 1}/{total_pages} with Qwen (this will take 60-120s)...")
                ocr_result = ocr_client.ocr_image(page_data.png_bytes, prompt_type="ocr_with_boxes")

                # Store in database
                db.store_page_result(
                    note_id,
                    page_num,
                    page_hash,
                    json.dumps(ocr_result.raw_response),
                    ocr_result.full_text,
                    ocr_result.processing_time_ms
                )

                # Save for injection
                page_results[page_num] = (ocr_result, page_data.width, page_data.height)

                logger.info(f"    Found {len(ocr_result.text_blocks)} text blocks, "
                           f"{len(ocr_result.full_text)} chars, "
                           f"{ocr_result.processing_time_ms:.0f}ms")
                pages_processed += 1

            except Exception as e:
                logger.error(f"  Error processing page {page_num}: {e}")
                processing_state["errors"].append(f"{note_path.name} page {page_num}: {str(e)}")
                pages_failed += 1

        # Inject OCR data back into .note file
        if WRITE_TO_NOTE and page_results:
            try:
                backup_dir = BACKUP_PATH if CREATE_BACKUPS else None
                inject_ocr_results(note_path, page_results, backup_dir, recogn_type=FILE_RECOGN_TYPE)
                logger.info(f"  Injected OCR data into {len(page_results)} pages")

                # IMPORTANT: Recompute hash after injection so we don't reprocess
                new_hash = compute_file_hash(note_path)
                new_stat = note_path.stat()
                db.upsert_note_file(
                    note_path,
                    new_hash,
                    new_stat.st_mtime,
                    new_stat.st_size,
                    total_pages
                )
                logger.debug(f"  Updated file hash after injection")
            except Exception as e:
                logger.error(f"  Failed to inject OCR data: {e}")
                processing_state["errors"].append(f"{note_path.name} injection: {str(e)}")

        # AI text cleanup if enabled (before exporting)
        cleaned_page_results = page_results
        if AI_TEXT_CLEANUP_ENABLED and page_results:
            try:
                from text_processor import cleanup_ocr_text_with_ai
                logger.info(f"  Cleaning up OCR text with AI...")
                
                cleaned_page_results = {}
                for page_num, (ocr_result, width, height) in page_results.items():
                    cleaned_text = cleanup_ocr_text_with_ai(ocr_result.full_text, ocr_client)
                    
                    # Create new OCRResult with cleaned text
                    cleaned_ocr = OCRResult(
                        text_blocks=ocr_result.text_blocks,
                        full_text=cleaned_text,
                        processing_time_ms=ocr_result.processing_time_ms,
                        raw_response=ocr_result.raw_response,
                        ocr_image_width=ocr_result.ocr_image_width,
                        ocr_image_height=ocr_result.ocr_image_height
                    )
                    cleaned_page_results[page_num] = (cleaned_ocr, width, height)
                
                logger.info(f"  Text cleanup completed")
            except Exception as e:
                logger.warning(f"  AI text cleanup failed, using original text: {e}")
                cleaned_page_results = page_results

        # Export OCR text to local .txt file if enabled
        if OCR_TXT_EXPORT_ENABLED and OCR_TXT_EXPORT_PATH and cleaned_page_results:
            try:
                # Collect full text from each page's OCR result (using cleaned text)
                page_texts = {
                    page_num: ocr_result.full_text
                    for page_num, (ocr_result, _, _) in cleaned_page_results.items()
                }
                export_path = export_ocr_text_to_file(
                    note_path,
                    page_texts,
                    Path(SUPERNOTE_DATA_PATH),
                    Path(OCR_TXT_EXPORT_PATH).expanduser()
                )
                if export_path:
                    logger.info(f"  Exported OCR text to {export_path}")
            except Exception as e:
                logger.error(f"  Failed to export OCR text: {e}")
                processing_state["errors"].append(f"{note_path.name} text export: {str(e)}")

        # Export searchable PDF with embedded OCR if enabled
        # Note: PDF uses original page_results (not cleaned) for bounding boxes
        pdf_path = None
        if OCR_PDF_EXPORT_ENABLED and OCR_PDF_EXPORT_PATH and page_results:
            try:
                pdf_path = export_note_to_pdf(
                    note_path,
                    page_results,  # Use original for bounding boxes
                    Path(SUPERNOTE_DATA_PATH),
                    Path(OCR_PDF_EXPORT_PATH).expanduser(),
                    debug_mode=PDF_DEBUG_MODE
                )
                if pdf_path:
                    logger.info(f"  Exported searchable PDF to {pdf_path}")
            except Exception as e:
                logger.error(f"  Failed to export PDF: {e}")
                processing_state["errors"].append(f"{note_path.name} PDF export: {str(e)}")

        # Export to Logseq markdown with PDF link if enabled
        if LOGSEQ_EXPORT_ENABLED and LOGSEQ_PAGES_PATH and LOGSEQ_ASSETS_PATH and cleaned_page_results:
            try:
                logseq_md_path = export_note_to_logseq(
                    note_path,
                    cleaned_page_results,  # Use cleaned text for Logseq
                    Path(SUPERNOTE_DATA_PATH),
                    Path(LOGSEQ_PAGES_PATH).expanduser(),
                    Path(LOGSEQ_ASSETS_PATH).expanduser(),
                    pdf_source_path=pdf_path,  # Pass PDF path if available
                    ocr_client=ocr_client  # Pass client for AI summary
                )
                if logseq_md_path:
                    logger.info(f"  Exported Logseq page to {logseq_md_path}")
            except Exception as e:
                logger.error(f"  Failed to export Logseq page: {e}")
                processing_state["errors"].append(f"{note_path.name} Logseq export: {str(e)}")

        # Update status based on results
        total_time = (time.time() - start_time) * 1000

        if pages_processed == 0 and pages_skipped == 0 and pages_failed > 0:
            # All pages failed to extract (e.g., unsupported format like custom PDF layers)
            error_msg = f"All {pages_failed} pages failed to extract"
            db.update_status(note_path, 'extraction_failed', error=error_msg)
            logger.warning(f"Extraction failed {note_path.name}: {error_msg}")
        else:
            db.update_status(note_path, 'completed')
            logger.info(f"Completed {note_path.name}: {pages_processed} processed, "
                       f"{pages_skipped} skipped, {pages_failed} failed, {total_time:.0f}ms")

        # Success only if we processed/skipped at least one page, or no pages failed
        success = not (pages_processed == 0 and pages_skipped == 0 and pages_failed > 0)

        return ProcessingResult(
            file_path=note_path,
            success=success,
            pages_processed=pages_processed,
            pages_skipped=pages_skipped,
            total_time_ms=total_time
        )

    except Exception as e:
        logger.exception(f"Failed to process {note_path}")
        db.update_status(note_path, 'failed', error=str(e))
        processing_state["errors"].append(f"{note_path.name}: {str(e)}")

        return ProcessingResult(
            file_path=note_path,
            success=False,
            pages_processed=0,
            pages_skipped=0,
            total_time_ms=(time.time() - start_time) * 1000,
            error=str(e)
        )
    finally:
        processing_state["current_file"] = None


def run_processing():
    """Run OCR processing on all .note files that need it."""
    global processing_state

    processing_state["status"] = "processing"
    processing_state["errors"] = []

    # Check OCR API availability
    logger.info("Checking OCR API availability...")
    if not ocr_client.health_check():
        logger.error("OCR API not available at %s", OCR_API_URL)
        logger.error("Start it with: ./scripts/start-ocr-api.sh")
        logger.error("Or install always-on mode: ./scripts/install-launchd.sh")
        processing_state["status"] = "error"
        processing_state["errors"].append("OCR API not available")
        return []

    logger.info("OCR API is ready")

    # Find .note files
    note_files = find_note_files()
    logger.info(f"Found {len(note_files)} .note files")

    if not note_files:
        processing_state["status"] = "idle"
        processing_state["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return []

    # Filter out recently uploaded files to prevent sync conflicts
    # Files uploaded by the device in the last 8 hours are "actively edited"
    # and should not be OCR'd until the user is done editing
    # Exception: SKIP_RECENT_CHECK=true bypasses this (used for 3am full run)
    if SKIP_RECENT_CHECK:
        logger.info("SKIP_RECENT_CHECK=true - processing all files regardless of upload time")
    else:
        recently_uploaded = sync_handler.get_recently_uploaded_files(minutes=480)
        if recently_uploaded:
            original_count = len(note_files)
            note_files = [f for f in note_files if f.name not in recently_uploaded]
            skipped = original_count - len(note_files)
            if skipped > 0:
                logger.info(f"Skipping {skipped} recently uploaded files to prevent sync conflicts")

    # Start processing run
    run_id = db.start_processing_run()

    # Process each file
    results = []
    total_files = len(note_files)
    for idx, note_path in enumerate(note_files, 1):
        logger.info(f"[{idx}/{total_files}] Checking {note_path.name}...")
        result = process_note_file(note_path)
        results.append(result)

    # Summarize
    successful = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)
    total_pages = sum(r.pages_processed for r in results)

    # Complete processing run
    db.complete_processing_run(
        run_id,
        files_scanned=len(note_files),
        files_processed=successful,
        files_skipped=0,
        files_failed=failed,
        total_pages=total_pages
    )

    processing_state["status"] = "idle"
    processing_state["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    processing_state["files_processed"] = successful
    processing_state["pages_processed"] = total_pages

    logger.info(f"Processing complete: {successful} files, {total_pages} pages, {failed} failed")

    # Update sync database for modified files (Mac App mode)
    # This ensures the Mac app knows files changed and will UPLOAD (not download)
    if sync_handler and WRITE_TO_NOTE:
        modified_files = [r.file_path for r in results if r.success and r.pages_processed > 0]
        if modified_files:
            logger.info(f"Updating sync database for {len(modified_files)} modified files...")
            updated, sync_failed = sync_handler.update_modified_files(modified_files)
            if sync_failed > 0:
                logger.warning(f"Sync database update: {updated} succeeded, {sync_failed} failed")

    return results


def run_health_server():
    """Run the health check server in a separate thread"""
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")


def main():
    """Main entry point"""
    global db, ocr_client, sync_handler

    logger.info("=" * 60)
    logger.info("Supernote OCR Enhancer starting...")
    logger.info("=" * 60)
    logger.info(f"OCR API URL: {OCR_API_URL}")
    logger.info(f"Supernote data path: {SUPERNOTE_DATA_PATH}")
    logger.info(f"Storage mode: {STORAGE_MODE or 'auto-detect'}")
    logger.info(f"Process interval: {PROCESS_INTERVAL}s (0 = single run)")
    logger.info(f"Write to .note files: {WRITE_TO_NOTE}")
    logger.info(f"Create backups: {CREATE_BACKUPS}")
    logger.info(f"Reset database: {RESET_DATABASE}")
    logger.info(f"FILE_RECOGN_TYPE: {FILE_RECOGN_TYPE}")
    logger.info(f"OCR PDF layers: {OCR_PDF_LAYERS}")
    logger.info(f"Text export enabled: {OCR_TXT_EXPORT_ENABLED}")
    if OCR_TXT_EXPORT_ENABLED:
        if OCR_TXT_EXPORT_PATH:
            logger.info(f"Text export path: {OCR_TXT_EXPORT_PATH}")
        else:
            logger.warning("Text export enabled but OCR_TXT_EXPORT_PATH not set - export disabled")
    logger.info(f"PDF export enabled: {OCR_PDF_EXPORT_ENABLED}")
    if OCR_PDF_EXPORT_ENABLED:
        if OCR_PDF_EXPORT_PATH:
            logger.info(f"PDF export path: {OCR_PDF_EXPORT_PATH}")
        else:
            logger.warning("PDF export enabled but OCR_PDF_EXPORT_PATH not set - export disabled")
    logger.info(f"Logseq export enabled: {LOGSEQ_EXPORT_ENABLED}")
    if LOGSEQ_EXPORT_ENABLED:
        if LOGSEQ_PAGES_PATH and LOGSEQ_ASSETS_PATH:
            logger.info(f"Logseq pages path: {LOGSEQ_PAGES_PATH}")
            logger.info(f"Logseq assets path: {LOGSEQ_ASSETS_PATH}")
        else:
            logger.warning("Logseq export enabled but paths not set - export disabled")
    logger.info(f"AI text cleanup enabled: {AI_TEXT_CLEANUP_ENABLED}")
    if AI_TEXT_CLEANUP_ENABLED:
        logger.info("AI cleanup requires Qwen model loaded in OCR API")
    logger.info(f"PDF debug mode: {PDF_DEBUG_MODE}")
    if PDF_DEBUG_MODE:
        logger.warning("PDF DEBUG MODE ENABLED - Bounding boxes will be visible in red!")

    # Ensure directories exist
    DATA_PATH.mkdir(parents=True, exist_ok=True)
    BACKUP_PATH.mkdir(parents=True, exist_ok=True)

    # Initialize database
    db = Database(DB_PATH)
    logger.info(f"Database initialized: {DB_PATH}")

    # Handle database reset if requested
    if RESET_DATABASE:
        logger.warning("RESET_DATABASE=true - Clearing all processing history!")
        db.reset_all_files()

    # Recover from any interrupted runs (stuck in 'processing' status)
    db.reset_stuck_processing()

    # Purge stale records for files that no longer exist
    existing_files = find_note_files()
    existing_paths = {str(f) for f in existing_files}
    purged = db.purge_missing_files(existing_paths)
    if purged > 0:
        logger.info(f"Cleaned up {purged} stale database records for deleted files")

    # Initialize OCR client
    ocr_client = OCRClient(OCR_API_URL)

    # Initialize sync handler (for updating Mac app or Personal Cloud database after OCR)
    try:
        sync_handler = create_sync_handler(
            mode=STORAGE_MODE or None,
            mac_app_database=MACAPP_DATABASE_PATH or None,
            mac_app_notes_path=MACAPP_NOTES_PATH or None,
            sync_server_compose=SYNC_SERVER_COMPOSE or None,
            sync_server_env=SYNC_SERVER_ENV or None
        )
        sync_status = sync_handler.get_status()
        logger.info(f"Sync handler: {sync_status.get('mode', 'unknown')} - {sync_status.get('status', 'unknown')}")
    except Exception as e:
        logger.warning(f"Sync handler initialization failed: {e} - continuing without sync")
        sync_handler = None

    # Start health server in background
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    logger.info("Health server started on port 8080")

    # Show initial stats
    stats = db.get_statistics()
    logger.info(f"Database stats: {json.dumps(stats, indent=2)}")

    if PROCESS_INTERVAL == 0:
        # Single run mode
        logger.info("Running in single-run mode")
        run_processing()
        logger.info("Single run complete. Exiting.")
    else:
        # Continuous mode
        logger.info(f"Running in continuous mode (interval: {PROCESS_INTERVAL}s)")
        while True:
            run_processing()
            logger.info(f"Sleeping for {PROCESS_INTERVAL}s...")
            time.sleep(PROCESS_INTERVAL)


if __name__ == "__main__":
    main()
