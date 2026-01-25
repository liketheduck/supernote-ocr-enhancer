# PDF Export Feature

## Overview

The Supernote OCR Enhancer can now generate **searchable PDFs** with embedded OCR layers. These PDFs contain:

- **Visible layer**: Original handwritten note images
- **Invisible layer**: OCR text with precise bounding boxes for search and indexing

This allows you to:
- 📄 Search your handwritten notes in any PDF viewer
- 🔍 Index PDFs in document management systems (DEVONthink, Evernote, etc.)
- 📱 Use Spotlight/macOS search to find text in your notes
- 🤖 Process notes with AI tools that require searchable text

## Configuration

Enable PDF export by setting these environment variables:

```bash
# Enable PDF export
export OCR_PDF_EXPORT_ENABLED="true"

# Set output directory for PDFs
export OCR_PDF_EXPORT_PATH="/Users/yourusername/supernote-pdf"
```

### In `run-native.sh`:

```bash
export OCR_PDF_EXPORT_ENABLED="true"
export OCR_PDF_EXPORT_PATH="$HOME/supernote-pdf"
```

### In Docker:

```yaml
environment:
  - OCR_PDF_EXPORT_ENABLED=true
  - OCR_PDF_EXPORT_PATH=/output/pdf
volumes:
  - ./pdf-output:/output/pdf
```

## Output Structure

PDFs are generated with the same directory structure as your Supernote files:

```
supernote-pdf/
├── Note/
│   ├── Meeting Notes.pdf
│   └── Ideas.pdf
├── Document/
│   └── Research.pdf
└── MyFolder/
    └── Project Notes.pdf
```

## How It Works

1. **Image Extraction**: Each page is extracted as a PNG image
2. **OCR Processing**: Text is recognized with precise bounding boxes
3. **PDF Generation**: 
   - Page size matches the original note dimensions
   - Handwritten image is placed as the visible layer
   - OCR text is overlaid invisibly with correct positioning
4. **Searchability**: PDF viewers can search and highlight text

## Technical Details

### Coordinate System

The PDF exporter handles two coordinate formats:

- **Percentage coordinates** (Qwen, OlmOCR): 0-100% of image dimensions
- **Pixel coordinates** (Vision Framework): Absolute pixel values

Both are converted to PDF coordinates (72 DPI) with proper scaling.

### Text Layer

The invisible OCR layer uses:
- Transparent white text (`alpha=0`)
- Font size calculated from bounding box height
- Precise positioning matching the handwritten text location

### Page Size

PDFs maintain the aspect ratio of Supernote pages:
- Default width: 612 points (8.5 inches at 72 DPI)
- Height: Calculated to maintain 1404x1872 aspect ratio

## Integration with Other Exports

PDF export works alongside existing export features:

```bash
# Export to all formats
export OCR_TXT_EXPORT_ENABLED="true"      # Plain text for PKMS
export OCR_TXT_EXPORT_PATH="/path/to/txt"

export OCR_PDF_EXPORT_ENABLED="true"      # Searchable PDFs
export OCR_PDF_EXPORT_PATH="/path/to/pdf"

export WRITE_TO_NOTE="true"               # Enhanced .note files
```

## Use Cases

### 1. Personal Knowledge Management (PKMS)

Export to both text and PDF for maximum flexibility:
- **Markdown/TXT**: For Obsidian, Logseq, Roam Research
- **PDF**: For DEVONthink, Evernote, OneNote

### 2. Document Archival

Create searchable archives of handwritten notes:
- PDFs are universally compatible
- OCR layer enables full-text search
- Original handwriting is preserved

### 3. AI Processing

Feed handwritten notes to AI tools:
- LLMs can extract text from searchable PDFs
- RAG systems can index PDF content
- Document analysis tools work with searchable PDFs

### 4. Sharing

Share notes while maintaining searchability:
- Recipients can search without OCR software
- Works on any device with a PDF viewer
- Professional appearance

## Performance

PDF generation is fast since it reuses OCR results:
- **Per page**: ~100-200ms (after OCR)
- **No re-processing**: Uses existing OCR data
- **Minimal overhead**: Generated during the same pass

## Troubleshooting

### PDFs not generated

Check that:
1. `OCR_PDF_EXPORT_ENABLED=true` is set
2. `OCR_PDF_EXPORT_PATH` points to a valid directory
3. You have write permissions to the output directory
4. Disk space is available

### Text not searchable

Verify:
1. OCR completed successfully (check logs)
2. PDF viewer supports text layers (most do)
3. Text blocks were found (check `text_blocks` count in logs)

### Incorrect text positioning

This can happen if:
1. Coordinate scaling is wrong (report as bug)
2. Image dimensions don't match OCR dimensions
3. PDF page size calculation is off

## Dependencies

PDF export requires:
- `reportlab>=4.0.0`: PDF generation library
- `pillow>=10.0.0`: Image handling (already required)

Install with:
```bash
pip install reportlab>=4.0.0
```

## Future Enhancements

Potential improvements:
- [ ] Configurable PDF page size
- [ ] Option to include only text (no images) for smaller files
- [ ] PDF/A format for long-term archival
- [ ] Metadata embedding (title, author, creation date)
- [ ] Bookmarks for multi-page notes
- [ ] Hyperlinks between pages
