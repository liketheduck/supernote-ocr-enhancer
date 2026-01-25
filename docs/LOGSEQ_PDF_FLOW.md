# Export Flow: PDF and Logseq

Visual diagram of how PDF export works with and without Logseq.

## 🔄 Scenario 1: PDF Export Only

```
┌─────────────────────────────────────────────────────────────┐
│  Configuration:                                             │
│  OCR_PDF_EXPORT_ENABLED=true                                │
│  OCR_PDF_EXPORT_PATH=~/Documents/SupernotePDFs              │
│  LOGSEQ_EXPORT_ENABLED=false                                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  OCR Processing                                             │
│  - Extract pages from .note                                 │
│  - Send to Vision Framework                                 │
│  - Get OCR results                                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  PDF Export                                                 │
│  ✅ Generate PDF in ~/Documents/SupernotePDFs/Work/Meeting.pdf│
└─────────────────────────────────────────────────────────────┘
                            ↓
                        ✅ DONE
```

**Result:**
- 1 PDF file in `~/Documents/SupernotePDFs/`
- Nothing generated for Logseq

---

## 🔄 Scenario 2: Logseq Export Only

```
┌─────────────────────────────────────────────────────────────┐
│  Configuration:                                             │
│  OCR_PDF_EXPORT_ENABLED=false                               │
│  LOGSEQ_EXPORT_ENABLED=true                                 │
│  LOGSEQ_PAGES_PATH=~/Documents/logseq/pages/supernote       │
│  LOGSEQ_ASSETS_PATH=~/Documents/logseq/assets               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  OCR Processing                                             │
│  - Extract pages from .note                                 │
│  - Send to Vision Framework                                 │
│  - Get OCR results                                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Logseq Export                                              │
│  ✅ Generate PDF in ~/logseq/assets/supernote/Work/Meeting.pdf│
│  ✅ Generate MD in ~/logseq/pages/supernote/Work/Meeting.md │
│     (with link to ../assets/supernote/Work/Meeting.pdf)    │
└─────────────────────────────────────────────────────────────┘
                            ↓
                        ✅ DONE
```

**Result:**
- 1 PDF file in `~/Documents/logseq/assets/supernote/`
- 1 MD file in `~/Documents/logseq/pages/supernote/`
- Link works correctly

---

## 🔄 Scenario 3: PDF Export + Logseq Export

```
┌─────────────────────────────────────────────────────────────┐
│  Configuration:                                             │
│  OCR_PDF_EXPORT_ENABLED=true                                │
│  OCR_PDF_EXPORT_PATH=~/Documents/SupernotePDFs              │
│  LOGSEQ_EXPORT_ENABLED=true                                 │
│  LOGSEQ_PAGES_PATH=~/Documents/logseq/pages/supernote       │
│  LOGSEQ_ASSETS_PATH=~/Documents/logseq/assets               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  OCR Processing                                             │
│  - Extract pages from .note                                 │
│  - Send to Vision Framework                                 │
│  - Get OCR results                                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  PDF Export                                                 │
│  ✅ Generate PDF in ~/Documents/SupernotePDFs/Work/Meeting.pdf│
│  📝 Save path: pdf_path = /path/to/SupernotePDFs/...        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Logseq Export                                              │
│  ✅ Copy PDF to ~/logseq/assets/supernote/Work/Meeting.pdf  │
│     (from pdf_path)                                         │
│  ✅ Generate MD in ~/logseq/pages/supernote/Work/Meeting.md │
│     (with link to ../assets/supernote/Work/Meeting.pdf)    │
└─────────────────────────────────────────────────────────────┘
                            ↓
                        ✅ DONE
```

**Result:**
- 1 PDF file in `~/Documents/SupernotePDFs/` (original)
- 1 PDF file in `~/Documents/logseq/assets/supernote/` (copy)
- 1 MD file in `~/Documents/logseq/pages/supernote/`
- Link works correctly
- **2 copies of the same PDF** (more space, but more flexible)

---

## 📊 Scenario Comparison

| Configuration | PDF in SupernotePDFs | PDF in Logseq Assets | MD in Logseq | Total PDFs |
|---------------|---------------------|---------------------|--------------|------------|
| **PDF Only** | ✅ | ❌ | ❌ | 1 |
| **Logseq Only** | ❌ | ✅ | ✅ | 1 |
| **Both** | ✅ | ✅ (copy) | ✅ | 2 |

## 🎯 Recommendations

### For Logseq Users

**Simple Option (Recommended):**
```bash
LOGSEQ_EXPORT_ENABLED=true
LOGSEQ_PAGES_PATH=~/Documents/logseq/pages/supernote
LOGSEQ_ASSETS_PATH=~/Documents/logseq/assets
```

**Advantages:**
- ✅ Less configuration
- ✅ Only 1 copy of PDF (saves space)
- ✅ Everything in Logseq

**Disadvantages:**
- ❌ No PDFs outside Logseq for sharing

---

**Complete Option:**
```bash
OCR_PDF_EXPORT_ENABLED=true
OCR_PDF_EXPORT_PATH=~/Documents/SupernotePDFs

LOGSEQ_EXPORT_ENABLED=true
LOGSEQ_PAGES_PATH=~/Documents/logseq/pages/supernote
LOGSEQ_ASSETS_PATH=~/Documents/logseq/assets
```

**Advantages:**
- ✅ PDFs in separate location (easy to share/backup)
- ✅ PDFs in Logseq (for links)
- ✅ Maximum flexibility

**Disadvantages:**
- ❌ 2 copies of the same PDF (uses more space)
- ❌ More configuration

---

### For Users Without Logseq

```bash
OCR_PDF_EXPORT_ENABLED=true
OCR_PDF_EXPORT_PATH=~/Documents/SupernotePDFs
```

**Advantages:**
- ✅ Simple
- ✅ Only 1 copy of PDF
- ✅ Easy to share

---

## 🔍 Technical Details

### Relevant Code (main.py)

```python
# Line 356-369: PDF Export
pdf_path = None
if OCR_PDF_EXPORT_ENABLED and OCR_PDF_EXPORT_PATH and page_results:
    pdf_path = export_note_to_pdf(...)  # Generate PDF
    # pdf_path now contains the path to the generated PDF

# Line 372-381: Logseq Export
if LOGSEQ_EXPORT_ENABLED and LOGSEQ_PAGES_PATH and LOGSEQ_ASSETS_PATH:
    export_note_to_logseq(
        ...
        pdf_source_path=pdf_path  # Pass the path (or None)
    )
```

### Relevant Code (logseq_exporter.py)

```python
# Line 175-195: PDF Handling
if pdf_source_path and pdf_source_path.exists():
    # Case 1: PDF already exists (generated by OCR_PDF_EXPORT)
    shutil.copy2(pdf_source_path, pdf_asset_path)
else:
    # Case 2: PDF doesn't exist, generate it directly
    export_note_to_pdf(
        note_path,
        page_results,
        supernote_data_path,
        logseq_assets_path / "supernote"
    )
```

### Decision Flow

```
Does pdf_source_path exist?
    ├─ YES → Copy existing PDF to Logseq assets
    └─ NO → Generate PDF directly in Logseq assets
```

---

## ❓ FAQ

**Q: Do I need `OCR_PDF_EXPORT_ENABLED=true` to use Logseq?**  
A: **NO**. Logseq generates its own PDF automatically if it doesn't exist.

**Q: What happens if I have both enabled?**  
A: 2 copies of the PDF are generated (one in `SupernotePDFs`, another in `logseq/assets`).

**Q: Which is more efficient?**  
A: Logseq only (1 PDF generated). With both, 1 PDF is generated and copied once.

**Q: Can I change configuration later?**  
A: Yes, but already generated files won't be moved automatically.

**Q: How do I remove duplicate PDFs?**  
A: Decide which location you prefer and delete the other manually.
