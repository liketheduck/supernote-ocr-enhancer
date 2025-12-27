# Claude Code Instructions

## CRITICAL: This is a PUBLIC Repository

**All commits are pushed to a PUBLIC GitHub repository.** Before committing or pushing, verify that no private information is exposed:

### Never include in commits:
- **Personal file names** (e.g., "Marriage.note", "Baby Care.note", "Job Applications.note")
- **Personal names** or identifiable information
- **Passwords, API keys, or secrets**
- **File paths containing usernames** (e.g., `/Users/dhays/...`)
- **Database contents** with personal data
- **Log snippets** containing personal information

### Before every commit:
1. Review `git diff --staged` for any personal information
2. Use generic examples instead of real file names (e.g., "MyNote.note" not "Marriage.note")
3. Sanitize any paths or database queries shown in documentation

### If private data is accidentally committed:
- It remains in git history even after removal
- Requires `git filter-branch` or `git filter-repo` + force push to fully remove
- GitHub may cache old commits - contact GitHub support if needed

## Project Context

This is the Supernote OCR Enhancer - processes .note files with Apple Vision Framework OCR.

Key files:
- `app/main.py` - Entry point
- `app/note_processor.py` - .note file handling
- `app/database.py` - SQLite state tracking
- `scripts/` - Helper scripts for OCR API management
