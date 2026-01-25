# Changelog

## [Version 1.1.0] - 2026-01-14

### ✨ **New Features**
- **Searchable PDF Export**: Generate PDFs with invisible OCR text layer for perfect search and indexing
- **Precise Bounding Boxes**: Fixed coordinate conversion for Qwen3-VL (0-1000 normalized coordinates)
- **Debug Mode**: Added `debug-pdf-bbox.sh` script for visual debugging of PDF coordinates

### 🐛 **Bug Fixes**
- **PDF Coordinate System**: Fixed fundamental issue where Qwen3-VL normalized coordinates (0-1000) were incorrectly treated as pixels
- **Text Alignment**: Corrected text positioning within PDF bounding boxes
- **Font Sizing**: Improved font size calculation for better text fit within bounding boxes

### 🔧 **Technical Improvements**
- Updated coordinate conversion logic to match `.note` file processing
- Added comprehensive logging for PDF coordinate debugging
- Improved error handling in PDF export

### 📝 **Documentation**
- Updated README.md with PDF export feature
- Cleaned up development documentation
- Maintained technical reference in `CLAUDE.md`

### 🧹 **Cleanup**
- Removed temporary development files
- Cleaned backup and log files
- Prepared repository for public release

---

## [Version 1.0.0] - 2026-01-13

### ✨ **Initial Release**
- Apple Vision Framework OCR integration
- Native macOS launchd scheduling
- Supernote .note file processing
- Word-level bounding boxes
- SQLite tracking system
- Backup protection
- Live sync server support
