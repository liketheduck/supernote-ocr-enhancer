"""
Database module for tracking processed .note files.
Uses SQLite for persistent state management.
"""

import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple
from dataclasses import dataclass
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class NoteFileRecord:
    id: int
    file_path: str
    file_hash: str
    file_mtime: float
    file_size: int
    page_count: Optional[int]
    processing_status: str
    last_processed_at: Optional[datetime]
    error_message: Optional[str]


@dataclass
class PageRecord:
    id: int
    note_file_id: int
    page_number: int
    page_hash: str
    ocr_result_json: Optional[str]
    ocr_text: Optional[str]
    processing_time_ms: Optional[float]
    processed_at: Optional[datetime]


class Database:
    """SQLite database for tracking .note file processing state."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        """Initialize database schema."""
        conn = self._get_connection()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS note_files (
                    id INTEGER PRIMARY KEY,
                    file_path TEXT UNIQUE NOT NULL,
                    file_hash TEXT NOT NULL,
                    file_mtime REAL NOT NULL,
                    file_size INTEGER NOT NULL,
                    page_count INTEGER,
                    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_checked_at TIMESTAMP,
                    last_processed_at TIMESTAMP,
                    processing_status TEXT DEFAULT 'pending',
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS page_processing (
                    id INTEGER PRIMARY KEY,
                    note_file_id INTEGER NOT NULL,
                    page_number INTEGER NOT NULL,
                    page_hash TEXT NOT NULL,
                    ocr_result_json TEXT,
                    ocr_text TEXT,
                    processing_time_ms REAL,
                    processed_at TIMESTAMP,
                    FOREIGN KEY (note_file_id) REFERENCES note_files(id),
                    UNIQUE(note_file_id, page_number)
                );

                CREATE TABLE IF NOT EXISTS processing_runs (
                    id INTEGER PRIMARY KEY,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    files_scanned INTEGER DEFAULT 0,
                    files_processed INTEGER DEFAULT 0,
                    files_skipped INTEGER DEFAULT 0,
                    files_failed INTEGER DEFAULT 0,
                    total_pages_processed INTEGER DEFAULT 0,
                    notes TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_note_files_status ON note_files(processing_status);
                CREATE INDEX IF NOT EXISTS idx_note_files_path ON note_files(file_path);
                CREATE INDEX IF NOT EXISTS idx_note_files_hash ON note_files(file_hash);
            """)
            conn.commit()
        finally:
            conn.close()

    def get_note_file(self, file_path: Path) -> Optional[NoteFileRecord]:
        """Get record for a .note file."""
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM note_files WHERE file_path = ?",
                (str(file_path),)
            ).fetchone()

            if row:
                return NoteFileRecord(
                    id=row['id'],
                    file_path=row['file_path'],
                    file_hash=row['file_hash'],
                    file_mtime=row['file_mtime'],
                    file_size=row['file_size'],
                    page_count=row['page_count'],
                    processing_status=row['processing_status'],
                    last_processed_at=row['last_processed_at'],
                    error_message=row['error_message']
                )
            return None
        finally:
            conn.close()

    def upsert_note_file(
        self,
        file_path: Path,
        file_hash: str,
        file_mtime: float,
        file_size: int,
        page_count: Optional[int] = None
    ) -> int:
        """Insert or update a .note file record."""
        conn = self._get_connection()
        try:
            conn.execute("""
                INSERT INTO note_files (file_path, file_hash, file_mtime, file_size, page_count, last_checked_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(file_path) DO UPDATE SET
                    file_hash = excluded.file_hash,
                    file_mtime = excluded.file_mtime,
                    file_size = excluded.file_size,
                    page_count = COALESCE(excluded.page_count, page_count),
                    last_checked_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
            """, (str(file_path), file_hash, file_mtime, file_size, page_count))
            conn.commit()

            row = conn.execute(
                "SELECT id FROM note_files WHERE file_path = ?",
                (str(file_path),)
            ).fetchone()
            return row['id']
        finally:
            conn.close()

    def update_status(
        self,
        file_path: Path,
        status: str,
        error: Optional[str] = None
    ):
        """Update processing status for a file."""
        conn = self._get_connection()
        try:
            if status == 'completed':
                conn.execute("""
                    UPDATE note_files
                    SET processing_status = ?,
                        last_processed_at = CURRENT_TIMESTAMP,
                        error_message = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE file_path = ?
                """, (status, str(file_path)))
            else:
                conn.execute("""
                    UPDATE note_files
                    SET processing_status = ?,
                        error_message = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE file_path = ?
                """, (status, error, str(file_path)))
            conn.commit()
        finally:
            conn.close()

    def should_process_file(self, file_path: Path, current_hash: str) -> Tuple[bool, str]:
        """
        Determine if a .note file needs processing.

        Returns: (should_process, reason)
        """
        record = self.get_note_file(file_path)

        if record is None:
            return True, "new_file"

        if record.file_hash != current_hash:
            return True, "content_changed"

        if record.processing_status == 'failed':
            return True, "retry_failed"

        if record.processing_status == 'completed':
            return False, "already_processed"

        if record.processing_status == 'processing':
            # Stuck from interrupted run - reset and retry
            return True, "interrupted_recovery"

        return True, "pending"

    def reset_all_files(self):
        """Reset all files to pending status for full reprocessing."""
        conn = self._get_connection()
        try:
            conn.execute("UPDATE note_files SET processing_status = 'pending'")
            conn.execute("DELETE FROM page_processing")
            conn.commit()
            logger.info("Reset all files for reprocessing")
        finally:
            conn.close()

    def reset_stuck_processing(self) -> int:
        """Reset files stuck in 'processing' status from interrupted runs."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "UPDATE note_files SET processing_status = 'pending' WHERE processing_status = 'processing'"
            )
            conn.commit()
            count = cursor.rowcount
            if count > 0:
                logger.info(f"Reset {count} stuck file(s) from interrupted run")
            return count
        finally:
            conn.close()

    def get_page_record(
        self,
        note_file_id: int,
        page_number: int
    ) -> Optional[PageRecord]:
        """Get processing record for a specific page."""
        conn = self._get_connection()
        try:
            row = conn.execute("""
                SELECT * FROM page_processing
                WHERE note_file_id = ? AND page_number = ?
            """, (note_file_id, page_number)).fetchone()

            if row:
                return PageRecord(
                    id=row['id'],
                    note_file_id=row['note_file_id'],
                    page_number=row['page_number'],
                    page_hash=row['page_hash'],
                    ocr_result_json=row['ocr_result_json'],
                    ocr_text=row['ocr_text'],
                    processing_time_ms=row['processing_time_ms'],
                    processed_at=row['processed_at']
                )
            return None
        finally:
            conn.close()

    def is_page_processed(
        self,
        note_file_id: int,
        page_number: int,
        current_hash: str
    ) -> bool:
        """Check if a page has already been processed with current content."""
        record = self.get_page_record(note_file_id, page_number)
        if record is None:
            return False
        return record.page_hash == current_hash and record.ocr_result_json is not None

    def store_page_result(
        self,
        note_file_id: int,
        page_number: int,
        page_hash: str,
        ocr_result_json: str,
        ocr_text: str,
        processing_time_ms: float
    ):
        """Store OCR result for a page."""
        conn = self._get_connection()
        try:
            conn.execute("""
                INSERT INTO page_processing
                    (note_file_id, page_number, page_hash, ocr_result_json, ocr_text, processing_time_ms, processed_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(note_file_id, page_number) DO UPDATE SET
                    page_hash = excluded.page_hash,
                    ocr_result_json = excluded.ocr_result_json,
                    ocr_text = excluded.ocr_text,
                    processing_time_ms = excluded.processing_time_ms,
                    processed_at = CURRENT_TIMESTAMP
            """, (note_file_id, page_number, page_hash, ocr_result_json, ocr_text, processing_time_ms))
            conn.commit()
        finally:
            conn.close()

    def start_processing_run(self) -> int:
        """Start a new processing run."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "INSERT INTO processing_runs DEFAULT VALUES"
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def complete_processing_run(
        self,
        run_id: int,
        files_scanned: int,
        files_processed: int,
        files_skipped: int,
        files_failed: int,
        total_pages: int,
        notes: Optional[str] = None
    ):
        """Complete a processing run."""
        conn = self._get_connection()
        try:
            conn.execute("""
                UPDATE processing_runs SET
                    completed_at = CURRENT_TIMESTAMP,
                    files_scanned = ?,
                    files_processed = ?,
                    files_skipped = ?,
                    files_failed = ?,
                    total_pages_processed = ?,
                    notes = ?
                WHERE id = ?
            """, (files_scanned, files_processed, files_skipped, files_failed, total_pages, notes, run_id))
            conn.commit()
        finally:
            conn.close()

    def get_statistics(self) -> dict:
        """Get processing statistics."""
        conn = self._get_connection()
        try:
            stats = {}

            row = conn.execute("SELECT COUNT(*) as total FROM note_files").fetchone()
            stats['total_files'] = row['total']

            for status in ['pending', 'processing', 'completed', 'failed']:
                row = conn.execute(
                    "SELECT COUNT(*) as count FROM note_files WHERE processing_status = ?",
                    (status,)
                ).fetchone()
                stats[status] = row['count']

            row = conn.execute(
                "SELECT COUNT(*) as count FROM page_processing WHERE ocr_result_json IS NOT NULL"
            ).fetchone()
            stats['pages_processed'] = row['count']

            return stats
        finally:
            conn.close()


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of file contents."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def compute_image_hash(image_bytes: bytes) -> str:
    """Compute SHA-256 hash of image data."""
    return hashlib.sha256(image_bytes).hexdigest()
