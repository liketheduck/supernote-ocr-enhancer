#!/usr/bin/env python3
"""
Modify FILE_RECOGN_TYPE flag in existing .note files without reprocessing OCR.
This lets us test which flag value enables highlighting on device.
"""

import sys
import io
import shutil
from pathlib import Path
from datetime import datetime

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import supernotelib as sn
import supernotelib.parser as parser
from note_processor import reconstruct_with_recognition


def modify_recogn_type(note_path: Path, new_value: str, backup: bool = True) -> None:
    """
    Modify FILE_RECOGN_TYPE flag in a .note file.

    Args:
        note_path: Path to .note file
        new_value: New value for FILE_RECOGN_TYPE ('0', '1', '2', etc.)
        backup: Create backup before modifying
    """
    print(f"\n{'='*60}")
    print(f"Processing: {note_path.name}")
    print(f"Setting FILE_RECOGN_TYPE = '{new_value}'")

    # Backup
    if backup:
        backup_path = note_path.with_suffix('.note.bak')
        shutil.copy2(note_path, backup_path)
        print(f"Backup: {backup_path}")

    # Load notebook
    notebook = sn.load_notebook(str(note_path))
    metadata = notebook.get_metadata()

    # Check current value
    if hasattr(metadata, 'header') and isinstance(metadata.header, dict):
        old_value = metadata.header.get('FILE_RECOGN_TYPE', 'not set')
        print(f"Current value: {old_value}")

        # Set new value
        metadata.header['FILE_RECOGN_TYPE'] = new_value
        print(f"New value: {new_value}")
    else:
        print("WARNING: No header or not a dict")
        return

    # Reconstruct WITHOUT disabling realtime recognition
    # (we're manually setting the flag value)
    from note_processor import pack_pages_with_recognition
    import supernotelib.manipulator as manip

    expected_signature = parser.SupernoteXParser.SN_SIGNATURES[-1]
    if metadata.signature != expected_signature:
        raise ValueError(f'Only latest file format supported')

    builder = manip.NotebookBuilder()
    manip._pack_type(builder, notebook)
    manip._pack_signature(builder, notebook)
    manip._pack_header(builder, notebook)
    manip._pack_cover(builder, notebook)
    manip._pack_keywords(builder, notebook)
    manip._pack_titles(builder, notebook)
    manip._pack_links(builder, notebook)
    manip._pack_backgrounds(builder, notebook)
    pack_pages_with_recognition(builder, notebook)
    manip._pack_footer(builder)
    manip._pack_tail(builder)
    manip._pack_footer_address(builder)

    reconstructed = builder.build()

    # Validate
    stream = io.BytesIO(reconstructed)
    xparser = parser.SupernoteXParser()
    try:
        _ = xparser.parse_stream(stream)
    except Exception as e:
        raise ValueError(f'Generated file fails validation: {e}')

    # Write back
    with open(note_path, 'wb') as f:
        f.write(reconstructed)

    print(f"✅ Successfully modified {note_path.name}")
    print(f"File size: {len(reconstructed):,} bytes")


def main():
    """Test different FILE_RECOGN_TYPE values."""

    base_path = Path("/Volumes/Storage/Supernote/INBOX/Note")

    # Test configurations
    configs = [
        ("Scrap.note", "0", "FILE_RECOGN_TYPE=0 (no realtime recognition - current broken state)"),
        ("Scrap2.note", "1", "FILE_RECOGN_TYPE=1 (realtime recognition ON - device might highlight)"),
        ("Scrap3.note", "2", "FILE_RECOGN_TYPE=2 (unknown - testing if this value exists)"),
        ("Scrap4.note", "3", "FILE_RECOGN_TYPE=3 (unknown - testing if this value exists)"),
    ]

    print("=" * 60)
    print("Modifying FILE_RECOGN_TYPE flags in test files")
    print("=" * 60)

    for filename, flag_value, description in configs:
        file_path = base_path / filename
        if not file_path.exists():
            print(f"\n❌ Not found: {filename}")
            continue

        print(f"\n{description}")
        try:
            modify_recogn_type(file_path, flag_value, backup=True)
        except Exception as e:
            print(f"❌ Error: {e}")

    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)
    print("Scrap.note  -> FILE_RECOGN_TYPE=0 (disabled - baseline broken)")
    print("Scrap2.note -> FILE_RECOGN_TYPE=1 (enabled - may work but device might redo OCR)")
    print("Scrap3.note -> FILE_RECOGN_TYPE=2 (testing unknown value)")
    print("Scrap4.note -> FILE_RECOGN_TYPE=3 (testing unknown value)")
    print("\nSync device and test search highlighting on each file!")


if __name__ == "__main__":
    main()
