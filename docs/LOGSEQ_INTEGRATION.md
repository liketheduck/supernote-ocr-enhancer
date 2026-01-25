# Logseq Integration

Export your Supernote notes to your Logseq knowledge graph with enhanced OCR, PDF links, and enriched metadata.

## 🎯 What It Does

Converts each processed `.note` file into:

1. **Logseq Page** (`.md`) with:
   - Link to PDF in assets
   - Metadata (date, source, OCR confidence)
   - Auto-generated tags
   - Automatic summary (if >3 pages)
   - Complete OCR text with formatting

2. **PDF in assets** (copy of exported PDF)
   - Located in `assets/supernote/...`
   - Same name and folder structure

## 📋 Configuration

### 1. Enable Logseq Export

Edit your `.env.local`:

```bash
# Enable Logseq export
LOGSEQ_EXPORT_ENABLED=true

# Path to your Logseq pages directory
# Pages will be created under pages/supernote/
LOGSEQ_PAGES_PATH=~/Documents/logseq/pages/supernote

# Path to your Logseq assets directory
# PDFs will be copied here
LOGSEQ_ASSETS_PATH=~/Documents/logseq/assets
```

### 2. PDF Export (Optional)

**Logseq works independently** - the PDF is generated automatically for Logseq even if you don't have `OCR_PDF_EXPORT_ENABLED=true`.

#### Option A: Logseq Only (simpler)

```bash
# Only enable Logseq
LOGSEQ_EXPORT_ENABLED=true
LOGSEQ_PAGES_PATH=~/Documents/logseq/pages/supernote
LOGSEQ_ASSETS_PATH=~/Documents/logseq/assets

# PDF export NOT needed
# OCR_PDF_EXPORT_ENABLED=false
```

**Result:**
- ✅ PDF is automatically generated in `logseq/assets/supernote/`
- ✅ Links work correctly
- ✅ Simpler (less configuration)

#### Option B: Logseq + Separate PDF Export (if you want PDFs elsewhere)

```bash
# Export PDFs to separate location
OCR_PDF_EXPORT_ENABLED=true
OCR_PDF_EXPORT_PATH=~/Documents/SupernotePDFs

# Logseq
LOGSEQ_EXPORT_ENABLED=true
LOGSEQ_PAGES_PATH=~/Documents/logseq/pages/supernote
LOGSEQ_ASSETS_PATH=~/Documents/logseq/assets
```

**Result:**
- ✅ PDF in `~/Documents/SupernotePDFs/` (for backup/sharing)
- ✅ PDF copied to `logseq/assets/supernote/` (for Logseq)
- ✅ Two copies of the same PDF (more space, but more flexible)

### 3. Complete Recommended Structure

```bash
# Text, PDF and Logseq exports
OCR_TXT_EXPORT_ENABLED=true
OCR_TXT_EXPORT_PATH=~/Documents/SupernoteText

OCR_PDF_EXPORT_ENABLED=true
OCR_PDF_EXPORT_PATH=~/Documents/SupernotePDFs

LOGSEQ_EXPORT_ENABLED=true
LOGSEQ_PAGES_PATH=~/Documents/logseq/pages/supernote
LOGSEQ_ASSETS_PATH=~/Documents/logseq/assets
```

## 📁 Generated File Structure

### Example: Note in Supernote

```
Supernote:
/user/Note/Work/Meeting-2026-01-13.note
```

### Generated Files

```
TXT:
~/Documents/SupernoteText/user/Note/Work/Meeting-2026-01-13.txt

PDF:
~/Documents/SupernotePDFs/user/Note/Work/Meeting-2026-01-13.pdf

Logseq Markdown:
~/Documents/logseq/pages/supernote/user/Note/Work/Meeting-2026-01-13.md

Logseq PDF Asset:
~/Documents/logseq/assets/supernote/user/Note/Work/Meeting-2026-01-13.pdf
```

## 📝 Logseq Page Format

### Example Output

```markdown
- [[📄 ../assets/supernote/user/Note/Work/Meeting-2026-01-13.pdf]]
  - **Processing date**: [[Jan 13th, 2026]]
  - **Source**: Supernote
  - **OCR confidence**: 94.2%
  - **Pages**: 5
  - **Words**: 342
  - **Tags**: #supernote #work #meeting
- ## Summary
  - Q1 2026 project planning meeting. Discussion of objectives, timeline and resource allocation. Action items identified for each team member.
- ## Content
  - ### Page 1
    - Q1 2026 Planning Meeting
    - Date: January 13, 2026
    - Attendees: John, Mary, Peter
  - ### Page 2
    - Quarter Objectives
    - 1. Launch new feature X
    - 2. Improve performance by 30%
    - 3. Reduce critical bugs to <5
  - ### Page 3
    - Timeline
    - January: Design and planning
    - February: Development
    - March: Testing and launch
  - ### Page 4
    - Resource Allocation
    - John: Backend development
    - Mary: Frontend + UX
    - Peter: QA + DevOps
  - ### Page 5
    - Action Items
    - [ ] John: Setup CI/CD pipeline
    - [ ] Mary: Create mockups
    - [ ] Peter: Define test strategy
```

## 🏷️ Auto-Generated Tags

### Based on Folder Structure

```
Path: /user/Note/Work/Projects/Alpha.note
Tags: #supernote #work #projects #alpha
```

### Based on Content (Heuristics)

The system detects keywords and adds relevant tags:

- **Meeting**: `#meeting` (detects: meeting, agenda, minutes)
- **Tasks**: `#tasks` (detects: todo, task, action item)
- **Ideas**: `#ideas` (detects: idea, brainstorm, concept)
- **Project**: `#project` (detects: project, plan, roadmap)

## 📊 Automatic Summary

### When It's Generated

- Only for notes with **more than 3 pages**
- Extracts the first 2-3 sentences of content
- Maximum 200 characters

### Example

```markdown
- ## Summary
  - Q1 2026 project planning meeting. Discussion of objectives, timeline and resource allocation.
```

## 🔗 Links in Logseq

### PDF Link

```markdown
- [[📄 ../assets/supernote/user/Note/Work/Meeting.pdf]]
```

Click the link → Opens the PDF in Logseq

### Date Link (Journal)

```markdown
- **Processing date**: [[Jan 13th, 2026]]
```

Click → Goes to your journal for that day

## 🔄 Complete Workflow

### With Manual Wrapper

```bash
# 1. Run wrapper
supernote-sync

# 2. Sync notes in Supernote Partner
# (wrapper waits)

# 3. Close Supernote Partner
# (wrapper detects and continues)

# 4. Automatic processing:
#    - OCR with Vision Framework
#    - Generate TXT
#    - Generate PDF
#    - Generate Logseq page
#    - Copy PDF to assets

# 5. Open Logseq
# Your notes are already in the graph
```

### With Automatic Cron

```bash
# Configure cron (once)
./scripts/install-ocr-enhancer-launchd.sh

# Then, automatically every 6 hours:
# - Detects new/modified files
# - Processes OCR
# - Exports to TXT, PDF and Logseq
# - Your notes appear in Logseq
```

## 🎨 Customization

### Modify Page Template

Edit `app/logseq_exporter.py`, function `export_note_to_logseq()`:

```python
# Line ~140: Build markdown
lines = []
lines.append(f"- [[📄 {pdf_rel_path}]]")
# Add your own fields here
lines.append(f"  - **Your field**: {your_value}")
```

### Improve Tag Generation

Edit `app/logseq_exporter.py`, function `generate_tags()`:

```python
# Line ~40: Add more keyword detection
if 'your_keyword' in text_lower:
    tags.append('your-tag')
```

### Improve Summary

Currently uses simple sentence extraction. To improve:

**Option 1: Use LLM (Qwen)**

```python
# In generate_summary()
# Call OCR API with summary prompt
summary = ocr_client.generate_summary(ocr_text)
```

**Option 2: Use NLP library**

```python
# Install: pip install sumy
from sumy.summarizers.lsa import LsaSummarizer
# Generate extractive summary
```

## 📈 Use Cases

### 1. Meeting Notes

```
Supernote → OCR → Logseq
- Tags: #meeting #work
- Link to PDF for reference
- Full-text search in Logseq
- Bidirectional links with other projects
```

### 2. Personal Journal

```
Supernote → OCR → Logseq
- Tags: #journal #personal
- Automatic link to day's journal
- Search by date
- Review past entries
```

### 3. Ideas and Brainstorming

```
Supernote → OCR → Logseq
- Tags: #ideas #brainstorm
- Connection with other concepts
- Evolution of ideas over time
- Export to other formats from Logseq
```

### 4. Study Notes

```
Supernote → OCR → Logseq
- Tags: #study #course-name
- Organization by topic
- Flashcards in Logseq
- Spaced repetition
```

## 🐛 Troubleshooting

### Pages Don't Appear in Logseq

**Problem**: `.md` files created but not visible in Logseq

**Solution**:
1. Verify that `LOGSEQ_PAGES_PATH` points to your correct graph
2. Re-index in Logseq: `Cmd+Shift+R` or menu "Re-index"
3. Check file permissions: `ls -la ~/Documents/logseq/pages/supernote/`

### PDF Links Don't Work

**Problem**: Clicking link doesn't open the PDF

**Solution**:
1. Verify the PDF exists: `ls ~/Documents/logseq/assets/supernote/`
2. Verify the relative path in the `.md`
3. Make sure `OCR_PDF_EXPORT_ENABLED=true`

### Tags Not Generated Correctly

**Problem**: Only `#supernote` appears, other tags missing

**Solution**:
1. Check the logs: `tail -f data/cron-ocr.log`
2. Verify OCR content has text: `cat file.txt`
3. Customize `generate_tags()` for your specific content

### Summary Not Generated

**Problem**: Notes with >3 pages don't have summary

**Solution**:
1. Verify OCR extracted text: `cat file.txt`
2. Check export logs
3. Adjust `generate_summary()` if format is incompatible

## 🔮 Future Improvements

### Planned

- [ ] Summary with LLM (Qwen) for better quality
- [ ] TODO detection and conversion to Logseq tasks
- [ ] Date detection and journal link creation
- [ ] Entity extraction (people, places, concepts)
- [ ] Suggestions for links to existing pages
- [ ] Language detection and multilingual metadata

### Contributions Welcome

If you implement any improvements, consider contributing to the project:
1. Fork the repository
2. Implement your feature
3. Add tests
4. Pull request with detailed description

## 📚 References

- [Logseq Documentation](https://docs.logseq.com/)
- [Logseq Markdown Format](https://docs.logseq.com/#/page/markdown)
- [Supernote OCR Enhancer README](../README.md)
- [PDF Export Documentation](./PDF_EXPORT.md)

## 💬 Support

If you have problems or suggestions:
1. Check the logs: `tail -f data/cron-ocr.log`
2. Verify configuration in `.env.local`
3. Open an issue on GitHub with details and logs
