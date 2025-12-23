"""
Sync Handler Module - Database synchronization for different Supernote storage modes.

Supports three storage modes:
1. personal_cloud (DEFAULT) - Self-hosted Supernote Cloud sync server (MariaDB)
2. mac_app - Official Supernote Mac app (local SQLite)
3. none - Manual file transfer, no sync database management

The default is Personal Cloud when SYNC_SERVER_COMPOSE/SYNC_SERVER_ENV are configured.
Mac app mode is an alternative for users of the official Supernote Mac application.

After OCR injection modifies .note files, the corresponding sync database must be
updated to prevent the sync system from thinking files are out of sync.
"""

import os
import sqlite3
import hashlib
import logging
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FileUpdateInfo:
    """Information about a modified file that needs sync database update."""
    file_path: Path
    new_size: int
    new_md5: str


def compute_file_md5(file_path: Path) -> str:
    """Compute MD5 hash of a file (required for Supernote sync databases)."""
    md5_hash = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()


class SyncHandler(ABC):
    """Abstract base class for sync database handlers."""

    @abstractmethod
    def update_modified_files(self, modified_files: List[Path]) -> Tuple[int, int]:
        """
        Update sync database for files that were modified by OCR injection.

        Args:
            modified_files: List of .note file paths that were modified

        Returns:
            Tuple of (updated_count, failed_count)
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this sync handler is properly configured and available."""
        pass

    @abstractmethod
    def get_status(self) -> dict:
        """Get status information about the sync system."""
        pass


class NoOpSyncHandler(SyncHandler):
    """
    No-op sync handler for when no sync database management is needed.

    Use this when:
    - Files are manually transferred (USB, file manager)
    - User doesn't have a sync server or Mac app configured
    """

    def update_modified_files(self, modified_files: List[Path]) -> Tuple[int, int]:
        logger.info("No sync database configured - skipping database update")
        return 0, 0

    def is_available(self) -> bool:
        return True

    def get_status(self) -> dict:
        return {"mode": "none", "status": "No sync database configured"}


class MacAppSyncHandler(SyncHandler):
    """
    Sync handler for the official Supernote Mac app.

    The Mac app stores sync state in a SQLite database at:
    ~/Library/Containers/com.ratta.supernote/Data/Library/Application Support/
    com.ratta.supernote/<USER_ID>/supernote.db

    The relevant table is `supernote_sqlite_info` with columns:
    - file_name: basename of the file
    - path: directory containing the file (absolute path)
    - local_s_h_a: MD5 hash of local file
    - server_s_h_a: MD5 hash on server (we set equal to local)
    - local_size: file size in bytes
    - server_size: file size on server (we set equal to local)
    """

    def __init__(self, database_path: Path, notes_base_path: Optional[Path] = None):
        """
        Initialize Mac App sync handler.

        Args:
            database_path: Path to supernote.db
            notes_base_path: Base path where .note files are stored (for path matching)
        """
        self.database_path = Path(database_path)
        self.notes_base_path = Path(notes_base_path) if notes_base_path else None

    def is_available(self) -> bool:
        """Check if the Mac app database exists and is accessible."""
        if not self.database_path.exists():
            logger.warning(f"Mac app database not found: {self.database_path}")
            return False

        try:
            conn = sqlite3.connect(str(self.database_path))
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='supernote_sqlite_info'"
            )
            exists = cursor.fetchone() is not None
            conn.close()
            return exists
        except Exception as e:
            logger.error(f"Failed to access Mac app database: {e}")
            return False

    def get_status(self) -> dict:
        """Get status information about the Mac app sync database."""
        if not self.is_available():
            return {
                "mode": "mac_app",
                "status": "unavailable",
                "database_path": str(self.database_path),
                "error": "Database not found or inaccessible"
            }

        try:
            conn = sqlite3.connect(str(self.database_path))
            cursor = conn.execute(
                "SELECT COUNT(*) FROM supernote_sqlite_info WHERE file_name LIKE '%.note'"
            )
            note_count = cursor.fetchone()[0]
            conn.close()

            return {
                "mode": "mac_app",
                "status": "available",
                "database_path": str(self.database_path),
                "note_files_tracked": note_count
            }
        except Exception as e:
            return {
                "mode": "mac_app",
                "status": "error",
                "database_path": str(self.database_path),
                "error": str(e)
            }

    def update_modified_files(self, modified_files: List[Path]) -> Tuple[int, int]:
        """
        Update the Mac app's SQLite database after OCR injection.

        CRITICAL: To trigger UPLOAD (not download), we must:
        - local_s_h_a = NEW hash (matches our modified file)
        - server_s_h_a = OLD hash (what server actually has) <- KEEP UNCHANGED
        - local_size = NEW size
        - server_size = OLD size <- KEEP UNCHANGED

        This signals to the app: "local file changed, server has old version, UPLOAD needed"
        If we set server_s_h_a = local_s_h_a, the app thinks they're in sync but then
        queries the real server, sees a mismatch, and DOWNLOADS (overwriting our changes).
        """
        if not modified_files:
            return 0, 0

        if not self.is_available():
            logger.error("Mac app database not available for sync update")
            return 0, len(modified_files)

        updated = 0
        failed = 0

        try:
            conn = sqlite3.connect(str(self.database_path))
            conn.row_factory = sqlite3.Row

            for file_path in modified_files:
                try:
                    file_path = Path(file_path)
                    if not file_path.exists():
                        logger.warning(f"File no longer exists: {file_path}")
                        failed += 1
                        continue

                    # Compute new hash and size
                    new_md5 = compute_file_md5(file_path)
                    new_size = file_path.stat().st_size
                    file_name = file_path.name
                    file_dir = str(file_path.parent) + "/"

                    # ONLY update local_s_h_a and local_size
                    # DO NOT touch server_s_h_a or server_size - keep them as old values
                    # This triggers UPLOAD: local differs from server, local is newer
                    cursor = conn.execute("""
                        UPDATE supernote_sqlite_info
                        SET local_s_h_a = ?,
                            local_size = ?
                        WHERE file_name = ? AND path = ?
                    """, (new_md5, str(new_size), file_name, file_dir))

                    if cursor.rowcount > 0:
                        logger.debug(f"Updated sync database (upload trigger): {file_name}")
                        updated += 1
                    else:
                        # Try to find by filename only (path might differ slightly)
                        cursor = conn.execute("""
                            UPDATE supernote_sqlite_info
                            SET local_s_h_a = ?,
                                local_size = ?
                            WHERE file_name = ?
                        """, (new_md5, str(new_size), file_name))

                        if cursor.rowcount > 0:
                            logger.debug(f"Updated sync database by name (upload trigger): {file_name}")
                            updated += 1
                        else:
                            logger.warning(f"File not found in sync database: {file_name}")
                            # Not a failure - file might be new or not synced yet
                            updated += 1  # Count as success since OCR was injected

                except Exception as e:
                    logger.error(f"Failed to update sync for {file_path}: {e}")
                    failed += 1

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Database error during sync update: {e}")
            return updated, len(modified_files) - updated

        logger.info(f"Mac app sync database updated: {updated} files updated, {failed} failed")
        return updated, failed


class PersonalCloudSyncHandler(SyncHandler):
    """
    Sync handler for self-hosted Supernote Personal Cloud sync server.

    The Personal Cloud uses MariaDB running in Docker with table `f_user_file`:
    - file_name: basename of the file
    - size: file size in bytes
    - md5: MD5 hash of the file
    - terminal_file_edit_time: timestamp in milliseconds

    This handler does NOT manage Docker start/stop - that's handled by
    run-with-sync-control.sh. This handler only updates the database.
    """

    def __init__(
        self,
        container_name: str = "supernote-mariadb",
        database_name: str = "supernotedb",
        username: str = "supernote",
        password: Optional[str] = None,
        data_path: Optional[Path] = None
    ):
        """
        Initialize Personal Cloud sync handler.

        Args:
            container_name: Docker container name for MariaDB
            database_name: MySQL database name
            username: MySQL username
            password: MySQL password (from MYSQL_PASSWORD env)
            data_path: Base path for .note files (for file lookup)
        """
        self.container_name = container_name
        self.database_name = database_name
        self.username = username
        self.password = password or os.getenv("MYSQL_PASSWORD", "")
        self.data_path = Path(data_path) if data_path else None

    def is_available(self) -> bool:
        """Check if MariaDB container is running and accessible."""
        try:
            result = subprocess.run(
                ["docker", "exec", self.container_name, "mysqladmin", "ping",
                 f"-u{self.username}", f"-p{self.password}"],
                capture_output=True,
                timeout=10
            )
            return result.returncode == 0
        except Exception as e:
            logger.debug(f"Personal Cloud database not available: {e}")
            return False

    def get_status(self) -> dict:
        """Get status of Personal Cloud sync database."""
        if not self.is_available():
            return {
                "mode": "personal_cloud",
                "status": "unavailable",
                "container": self.container_name,
                "error": "MariaDB container not running or not accessible"
            }

        try:
            # Get count of note files
            result = subprocess.run(
                ["docker", "exec", self.container_name, "mysql",
                 f"-u{self.username}", f"-p{self.password}", self.database_name,
                 "-N", "-e", "SELECT COUNT(*) FROM f_user_file WHERE file_name LIKE '%.note' AND is_active = 'Y';"],
                capture_output=True,
                text=True,
                timeout=10
            )
            note_count = int(result.stdout.strip()) if result.returncode == 0 else 0

            return {
                "mode": "personal_cloud",
                "status": "available",
                "container": self.container_name,
                "note_files_tracked": note_count
            }
        except Exception as e:
            return {
                "mode": "personal_cloud",
                "status": "error",
                "container": self.container_name,
                "error": str(e)
            }

    def update_modified_files(self, modified_files: List[Path]) -> Tuple[int, int]:
        """
        Update Personal Cloud MariaDB database after OCR injection.

        Note: This is typically called by run-with-sync-control.sh after
        the OCR enhancer completes. The script handles Docker orchestration.
        """
        if not modified_files:
            return 0, 0

        if not self.is_available():
            logger.error("Personal Cloud database not available for sync update")
            return 0, len(modified_files)

        updated = 0
        failed = 0
        import time
        current_ts = int(time.time() * 1000)  # milliseconds

        for file_path in modified_files:
            try:
                file_path = Path(file_path)
                if not file_path.exists():
                    logger.warning(f"File no longer exists: {file_path}")
                    failed += 1
                    continue

                new_md5 = compute_file_md5(file_path)
                new_size = file_path.stat().st_size
                file_name = file_path.name

                # Update the database record
                update_sql = f"""
                    UPDATE f_user_file
                    SET size = {new_size},
                        md5 = '{new_md5}',
                        terminal_file_edit_time = {current_ts},
                        update_time = NOW()
                    WHERE file_name = '{file_name}' AND is_active = 'Y';
                """

                result = subprocess.run(
                    ["docker", "exec", self.container_name, "mysql",
                     f"-u{self.username}", f"-p{self.password}", self.database_name,
                     "-e", update_sql],
                    capture_output=True,
                    text=True,
                    timeout=10
                )

                if result.returncode == 0:
                    logger.debug(f"Updated Personal Cloud sync: {file_name}")
                    updated += 1
                else:
                    logger.error(f"Failed to update {file_name}: {result.stderr}")
                    failed += 1

            except Exception as e:
                logger.error(f"Failed to update sync for {file_path}: {e}")
                failed += 1

        logger.info(f"Personal Cloud sync updated: {updated} files, {failed} failed")
        return updated, failed


def create_sync_handler(
    mode: Optional[str] = None,
    mac_app_database: Optional[str] = None,
    mac_app_notes_path: Optional[str] = None,
    personal_cloud_container: str = "supernote-mariadb",
    personal_cloud_password: Optional[str] = None,
    personal_cloud_data_path: Optional[str] = None,
    sync_server_compose: Optional[str] = None,
    sync_server_env: Optional[str] = None
) -> SyncHandler:
    """
    Factory function to create appropriate sync handler based on configuration.

    Priority (respects Personal Cloud as default when configured):
    1. If mode is explicitly set, use that mode
    2. If SYNC_SERVER_COMPOSE is configured, default to personal_cloud
    3. If mac_app paths are provided, use mac_app
    4. Otherwise, use no-op handler (manual file transfer)

    Args:
        mode: Explicit mode override ("none", "mac_app", or "personal_cloud")
        mac_app_database: Path to Mac app's supernote.db
        mac_app_notes_path: Path to Mac app's Supernote folder
        personal_cloud_container: Docker container name for MariaDB
        personal_cloud_password: MySQL password
        personal_cloud_data_path: Base path for .note files
        sync_server_compose: Path to sync server's docker-compose.yml
        sync_server_env: Path to sync server's .env file

    Returns:
        Appropriate SyncHandler instance
    """
    # Explicit mode takes priority
    if mode:
        mode = mode.lower()
        if mode == "none":
            logger.info("Using no-op sync handler (explicit mode=none)")
            return NoOpSyncHandler()
        elif mode == "mac_app":
            if not mac_app_database:
                # Try auto-detection
                detected = auto_detect_mac_app_database()
                if detected:
                    mac_app_database = str(detected)
                    logger.info(f"Auto-detected Mac app database: {mac_app_database}")
                else:
                    raise ValueError("mac_app mode requires MACAPP_DATABASE_PATH or auto-detection")
            logger.info(f"Using Mac app sync handler: {mac_app_database}")
            return MacAppSyncHandler(
                database_path=Path(mac_app_database),
                notes_base_path=Path(mac_app_notes_path) if mac_app_notes_path else None
            )
        elif mode == "personal_cloud":
            logger.info(f"Using Personal Cloud sync handler: {personal_cloud_container}")
            return PersonalCloudSyncHandler(
                container_name=personal_cloud_container,
                password=personal_cloud_password,
                data_path=Path(personal_cloud_data_path) if personal_cloud_data_path else None
            )
        else:
            raise ValueError(f"Unknown sync mode: {mode}. Use 'none', 'mac_app', or 'personal_cloud'")

    # No explicit mode - determine from configuration
    # Personal Cloud is the DEFAULT when sync server is configured
    if sync_server_compose and os.path.exists(sync_server_compose):
        logger.info(f"Personal Cloud configured (default) - sync server: {sync_server_compose}")
        return PersonalCloudSyncHandler(
            container_name=personal_cloud_container,
            password=personal_cloud_password,
            data_path=Path(personal_cloud_data_path) if personal_cloud_data_path else None
        )

    # Check for Mac app configuration
    if mac_app_database and os.path.exists(mac_app_database):
        logger.info(f"Using Mac app sync handler: {mac_app_database}")
        return MacAppSyncHandler(
            database_path=Path(mac_app_database),
            notes_base_path=Path(mac_app_notes_path) if mac_app_notes_path else None
        )

    # No sync configuration - use no-op
    logger.info("No sync database configured - using no-op handler")
    return NoOpSyncHandler()


def auto_detect_mac_app_path() -> Optional[Path]:
    """
    Auto-detect the Supernote Mac app data path.

    Returns the path to the user data directory if found, or None.
    The structure is:
    ~/Library/Containers/com.ratta.supernote/Data/Library/Application Support/
    com.ratta.supernote/<USER_ID>/

    Where <USER_ID> is a numeric directory.
    """
    base_path = Path.home() / "Library/Containers/com.ratta.supernote/Data/Library/Application Support/com.ratta.supernote"

    if not base_path.exists():
        return None

    # Find user ID directory (numeric)
    for item in base_path.iterdir():
        if item.is_dir() and item.name.isdigit():
            return item

    return None


def auto_detect_mac_app_database() -> Optional[Path]:
    """
    Auto-detect the Supernote Mac app database path.

    Returns the path to supernote.db if found, or None.
    """
    user_dir = auto_detect_mac_app_path()
    if user_dir:
        db_path = user_dir / "supernote.db"
        if db_path.exists():
            return db_path
    return None


def auto_detect_mac_app_notes() -> Optional[Path]:
    """
    Auto-detect the Supernote Mac app notes directory.

    Returns the path to the Supernote folder if found, or None.
    """
    user_dir = auto_detect_mac_app_path()
    if user_dir:
        notes_path = user_dir / "Supernote"
        if notes_path.exists():
            return notes_path
    return None
