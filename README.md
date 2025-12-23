# Supernote OCR Enhancer

Docker container that processes Supernote `.note` files using Apple Vision Framework OCR to replace Supernote's built-in OCR (~27% word error rate) with high-quality Vision Framework OCR (~5% word error rate) and pixel-perfect bounding boxes for search highlighting.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Your Mac (Apple Silicon)                    │
│                                                                      │
│  ┌────────────────────────┐      ┌───────────────────────────────┐  │
│  │  supernote-ocr-        │      │  ocr-api (native macOS)       │  │
│  │  enhancer (Docker)     │─────▶│  Apple Vision Framework      │  │
│  │                        │      │  localhost:8100               │  │
│  │  - Extracts pages      │      │                               │  │
│  │  - Tracks state (SQLite)│     │  - Native macOS OCR          │  │
│  │  - Injects OCR back    │      │  - Word-level bboxes         │  │
│  └──────────┬─────────────┘      └───────────────────────────────┘  │
│             │                                                        │
│             ▼                                                        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Your Supernote data directory                                │   │
│  │  (.note files - synced from Supernote devices)                │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## Features

- **High-quality OCR**: Replaces Supernote's built-in OCR with Apple Vision Framework (+41.8% more text captured)
- **Fast processing**: 0.8 seconds per page average (150x faster than Qwen2.5-VL)
- **Accurate bounding boxes**: Word-level bounding boxes enable search highlighting on device
- **Smart tracking**: SQLite database tracks file hashes to avoid reprocessing unchanged files
- **Backup protection**: Creates timestamped backups before modifying any file
- **Sync server coordination**: Optionally stops Supernote sync server during processing to prevent conflicts
- **Proper coordinate system**: Uses device's native coordinate system (PNG pixels ÷ 11.9) for perfect highlighting
- **Battery-friendly**: TYPE='0' configuration prevents device from re-OCRing after pen strokes

## Performance

**Production test results** (111 files, 303 pages):
- **Processing time**: 4.1 minutes total
- **Speed**: 0.8 seconds per page average, 2.2 seconds per file
- **Success rate**: 96.5% (111/115 files completed)
- **Accuracy**: +41.8% more text captured vs Supernote device OCR
- **vs Qwen2.5-VL 7B**: 150x faster, 31.5% less text (optimal trade-off for batch processing)

See [FINAL_OCR_COMPARISON_REPORT.md](data/FINAL_OCR_COMPARISON_REPORT.md) for detailed accuracy analysis.

## Prerequisites

1. **Apple Silicon Mac** (M1/M2/M3/M4) - Required for Apple Vision Framework
2. **macOS 13+ (Ventura or later)** - Required for Vision Framework OCR
3. **Docker Desktop** installed
4. **OCR API server** running locally (see [OCR API Setup](#ocr-api-setup))
5. **Supernote .note files** synced to your Mac

## Quick Start

### 1. Clone and Configure

```bash
git clone https://github.com/liketheduck/supernote-ocr-enhancer.git
cd supernote-ocr-enhancer

# Create local configuration
cp .env.example .env.local

# Edit .env.local with your paths
nano .env.local
```

Required settings in `.env.local`:
```bash
# REQUIRED: Path to your Supernote .note files
SUPERNOTE_DATA_PATH=/path/to/your/supernote/data

# OPTIONAL: Only if using Supernote Cloud sync server
# (See "Supernote Cloud / Sync Server" section below)
SYNC_SERVER_COMPOSE=/path/to/supernote-cloud/docker-compose.yml
SYNC_SERVER_ENV=/path/to/supernote-cloud/.env
```

### 2. Build the Container

```bash
docker compose build
```

### 3. Start the OCR API

You need a local MLX-VLM OCR API running. See [OCR API Setup](#ocr-api-setup) below.

### 4. Run OCR Enhancement

**If you DON'T use a Supernote sync server** (manual file transfer):
```bash
docker compose run --rm ocr-enhancer python /app/main.py
```

**If you USE a Supernote sync server** (REQUIRED to prevent file corruption):
```bash
./run-with-sync-control.sh
```

> **WARNING**: Running OCR enhancement while the sync server is active can corrupt your .note files. The `run-with-sync-control.sh` script automatically stops the sync server, runs OCR, syncs the database, and restarts the server.

**Dry run** (see what would happen):
```bash
./run-with-sync-control.sh --dry-run
```

## OCR API Setup

The OCR API is a separate service that runs **natively on macOS** (not in Docker) to access Apple's Vision Framework. You must set this up before running the enhancer.

### Using uv (recommended)

```bash
# Create OCR API directory
mkdir -p ~/services/ocr-api
cd ~/services/ocr-api

# Initialize with uv
uv init --name ocr-api --python 3.11

# Install dependencies
# CRITICAL: ocrmac is required for Apple Vision Framework OCR
uv add ocrmac pillow fastapi uvicorn python-multipart

# Optional: Add mlx-vlm for Qwen2.5-VL OCR (slower but more accurate)
# uv add mlx-vlm

# Copy server.py from this repo
cp /path/to/supernote-ocr-enhancer/examples/server.py .

# Create logs directory
mkdir -p logs

# Start the server
uv run python server.py
```

### What Gets Installed

| Package | Purpose | Required? |
|---------|---------|-----------|
| `ocrmac` | Apple Vision Framework OCR with word-level bounding boxes | **Yes** |
| `pillow` | Image processing | **Yes** |
| `fastapi` | REST API server | **Yes** |
| `uvicorn` | ASGI server | **Yes** |
| `python-multipart` | File upload support | **Yes** |
| `mlx-vlm` | Qwen2.5-VL models (optional, for `/ocr` endpoint) | No |

### Verify Installation

```bash
# Check if server is running
curl http://localhost:8100/health

# Check available endpoints
curl http://localhost:8100/prompts
```

The `/prompts` endpoint will show `"vision_available": true` if `ocrmac` is properly installed.

### OCR Endpoints

| Endpoint | OCR Engine | Speed | Accuracy | Use Case |
|----------|------------|-------|----------|----------|
| `/ocr/vision` | Apple Vision Framework | **0.8s/page** | Good (+41.8% vs Supernote) | **Default - batch processing** |
| `/ocr` | Qwen2.5-VL 7B (requires mlx-vlm) | 60-120s/page | Best (+107% vs Supernote) | Single files needing max accuracy |

This project uses `/ocr/vision` by default for its speed advantage.

### Troubleshooting ocrmac

If Vision OCR isn't working:

```bash
# Verify ocrmac is installed
uv run python -c "from ocrmac.ocrmac import OCR; print('ocrmac OK')"

# If you get import errors, try reinstalling
uv remove ocrmac && uv add ocrmac
```

`ocrmac` requires macOS 10.15+ and works best on macOS 13+ (Ventura).

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SUPERNOTE_DATA_PATH` | (required) | Path to .note files on host |
| `OCR_API_URL` | `http://host.docker.internal:8100` | OCR API endpoint |
| `PROCESS_INTERVAL` | `0` | Seconds between runs (0 = single run) |
| `LOG_LEVEL` | `INFO` | Logging level |
| `WRITE_TO_NOTE` | `true` | Write OCR data back to files |
| `CREATE_BACKUPS` | `true` | Create backups before modifying |
| `RESET_DATABASE` | `false` | Clear all history and reprocess every file |

## How It Works

1. **Scan**: Finds all `.note` files in the data directory
2. **Track**: Uses SQLite to track file/page hashes and avoid reprocessing
3. **Extract**: Converts each page to PNG (1920x2560) using supernotelib
4. **OCR**: Sends full-resolution images to Apple Vision Framework via OCR API for word-level text recognition with pixel-accurate bounding boxes
5. **Transform**: Converts Vision Framework coordinates (PNG pixels) to Supernote's coordinate system (PNG pixels ÷ 11.9)
6. **Inject**: Writes enhanced OCR data into the `.note` file's RECOGNTEXT block with proper coordinate format
7. **Enable highlighting**: Sets `FILE_RECOGN_TYPE=0` and `FILE_RECOGN_LANGUAGE=en_US` so device uses OCR for search highlighting while preserving our enhanced OCR

### Critical: FILE_RECOGN_TYPE='0' vs '1'

**The Discovery**: Through comprehensive testing, we discovered that `FILE_RECOGN_TYPE='0'` is the optimal setting:

| Setting | Highlighting Works? | Device Re-OCRs? | Battery Impact | Our Choice |
|---------|---------------------|-----------------|----------------|------------|
| TYPE='0' | ✅ Yes | ❌ No | Low (no re-OCR) | **✅ Default** |
| TYPE='1' | ✅ Yes | ✅ Yes | High (re-OCRs after pen strokes) | ❌ Not used |

**Why TYPE='0'?**
1. **Preserves our OCR**: Device doesn't overwrite Vision Framework OCR with its lower-quality OCR (~27% WER)
2. **Saves battery**: Device doesn't re-run OCR after every pen stroke
3. **Highlighting still works**: Search highlighting is fully functional
4. **Trade-off**: Device must sync to computer before search highlighting updates (acceptable for our use case)

**Testing revealed**:
- `LANG='none'` causes "redownload language" prompt (never use)
- `LANG=''` (empty) works but provides no benefit over `LANG='en_US'`
- `RECOGNSTATUS` value doesn't affect device behavior (new pen strokes always trigger OCR with TYPE='1')

### Critical: Supernote Coordinate System Discovery

**The Problem**: Search highlighting wasn't working - highlights appeared in wrong positions or not at all.

**The Solution**: By analyzing a device-generated OCR file, we discovered Supernote uses a scaled coordinate system:
- **Vision Framework returns**: Bounding boxes in PNG pixel coordinates (e.g., x=420, y=711)
- **Supernote expects**: Coordinates in a scaled system = **PNG pixels ÷ 11.9** (e.g., x=35.34, y=59.72)

**Why 11.9?** Empirically determined by comparing device OCR coordinates to Vision Framework coordinates for the same text. The ratio is consistently ~11.9x.

**Example transformation**:
```python
# Vision Framework output (pixels)
bbox = [420.47, 710.70, 963.73, 900.47]  # [left, top, right, bottom]

# Convert to Supernote format
x = 420.47 / 11.9 = 35.33
y = 710.70 / 11.9 = 59.72
width = (963.73 - 420.47) / 11.9 = 45.65
height = (900.47 - 710.70) / 11.9 = 15.95

# Supernote format
{"bounding-box": {"x": 35.33, "y": 59.72, "width": 45.65, "height": 15.95}, "label": "word"}
```

This transformation is **critical** for search highlighting to work correctly on the device.

## Storage Mode Options

This tool supports three ways to access your Supernote .note files:

| Mode | Description | When to Use |
|------|-------------|-------------|
| **Personal Cloud** | Self-hosted Supernote Cloud sync server | Power users with docker-based sync |
| **Mac App** | Official Supernote Mac application | Users of the desktop Mac app |
| **Manual** | Direct file access (USB, file manager) | Simple setups without sync |

### Quick Decision Guide

- **Using the official Supernote Mac app?** → Use [Mac App Mode](#supernote-mac-app)
- **Using a self-hosted sync server?** → Use [Personal Cloud Mode](#supernote-cloud--sync-server) (default)
- **Manually copying files via USB?** → Use [Manual Mode](#manual-file-transfer)

---

## Supernote Mac App

If you use the official **Supernote Partner** Mac app to sync your notes, use this mode.

### How It Works

The Mac app stores your .note files and sync state locally:
```
~/Library/Containers/com.ratta.supernote/Data/Library/Application Support/
com.ratta.supernote/<USER_ID>/
├── supernote.db          # SQLite sync database
├── Supernote/            # Your .note files
│   ├── Note/
│   ├── Document/
│   └── ...
```

**Sync mechanism:** When we modify a .note file, we update the Mac app's SQLite database to set `local_s_h_a` (local file hash) to the new hash while keeping `server_s_h_a` (server hash) unchanged. This signals to the app: "local file changed, server has old version → UPLOAD needed". The app then pushes the OCR-enhanced file to Supernote's cloud instead of downloading the old version.

### Critical: Quit the App During Processing

**You MUST quit Supernote Partner before running OCR enhancement.** If the app is running:
- It may sync mid-processing and download old files from the server
- It holds locks on the SQLite database
- File changes may not be detected correctly

The `run-with-macapp.sh` script will prompt you to quit the app. For automated runs, use the cron template which handles this automatically.

### Quick Start (Mac App)

**Option 1: Auto-Detection (Recommended)**

```bash
# Auto-detects your Mac app paths - no configuration needed!
./run-with-macapp.sh --auto
```

**Option 2: Manual Configuration**

```bash
# 1. Find your user ID (long numeric string)
ls ~/Library/Containers/com.ratta.supernote/Data/Library/Application\ Support/com.ratta.supernote/

# 2. Configure .env.local
cat >> .env.local << 'EOF'
STORAGE_MODE=mac_app
MACAPP_NOTES_PATH=~/Library/Containers/com.ratta.supernote/Data/Library/Application Support/com.ratta.supernote/YOUR_USER_ID/Supernote
MACAPP_DATABASE_PATH=~/Library/Containers/com.ratta.supernote/Data/Library/Application Support/com.ratta.supernote/YOUR_USER_ID/supernote.db
EOF

# 3. Run OCR enhancement (quit the app first!)
./run-with-macapp.sh
```

### Mac App Script Options

```bash
./run-with-macapp.sh              # Normal run (prompts to quit app)
./run-with-macapp.sh --auto       # Auto-detect paths (no config needed)
./run-with-macapp.sh --dry-run    # Preview what would happen
```

### Scheduling Mac App OCR (Cron Job)

For automatic nightly OCR processing, use the provided cron template. **This template automatically quits and restarts Supernote Partner** to prevent sync conflicts.

```bash
# 1. Copy the template
cp scripts/cron-macapp-template.sh ~/scripts/supernote-ocr-cron.sh

# 2. Edit and set your OCR_ENHANCER_DIR path
nano ~/scripts/supernote-ocr-cron.sh

# 3. Make executable
chmod +x ~/scripts/supernote-ocr-cron.sh

# 4. Add to crontab (runs daily at midnight)
crontab -e
```

Add this line to your crontab:
```
0 0 * * * /Users/YOUR_USERNAME/scripts/supernote-ocr-cron.sh >> /tmp/supernote-ocr.log 2>&1
```

**What the cron job does:**
1. Quits Supernote Partner (gracefully, then force-kill if needed)
2. Waits for the app to fully close
3. Runs OCR enhancement on all .note files
4. Updates the database to trigger upload
5. Restarts Supernote Partner
6. App syncs enhanced files to Supernote cloud

**Important:** Mac App cron runs on your Mac (host), not inside Docker. This is completely separate from Personal Cloud cron which runs inside the Docker container.

### Notes for Mac App Users

1. **App name**: The Mac app is called "**Supernote Partner**" (not just "Supernote").

2. **Sync behavior**: After OCR enhancement, when you open Supernote Partner, it will **upload** your enhanced files to the cloud (not download old versions).

3. **File tracking**: Files are tracked by path and content hash. Files are only re-processed if their content changes.

4. **No Docker orchestration**: Unlike Personal Cloud mode, Mac App mode doesn't stop/start Docker services. It only updates the local SQLite database.

---

## Supernote Cloud / Sync Server

If you use a **self-hosted Supernote Cloud sync server** (like [supernote-cloud-docker](https://github.com/philips/supernote-cloud-docker)), use this mode. This is the **default** when sync server settings are configured.

### Do I need this?

- **If you manually transfer files** (USB, file manager): You don't need a sync server. Just point `SUPERNOTE_DATA_PATH` to your .note files.
- **If you use the Mac app**: See [Supernote Mac App](#supernote-mac-app) section above.
- **If you use a self-hosted sync server**: You need to coordinate with it to prevent conflicts.

### What is the Supernote Sync Server?

The [Supernote Cloud](https://github.com/philips/supernote-cloud-docker) or similar self-hosted sync server syncs .note files between your device and Mac. When this tool modifies .note files (injecting OCR), the sync server's database becomes out of sync with the filesystem, causing conflicts.

### Sync Server Coordination

The `run-with-sync-control.sh` script handles this automatically:

1. Stops the sync server before processing
2. Runs the OCR enhancer
3. Updates the sync server's MariaDB database with new file sizes/hashes
4. Restarts the sync server

Configure in `.env.local`:
```bash
# Path to your sync server's docker-compose.yml
SYNC_SERVER_COMPOSE=/path/to/supernote-cloud/docker-compose.yml

# Path to your sync server's .env (contains database password)
SYNC_SERVER_ENV=/path/to/supernote-cloud/.env
```

If not using a sync server, leave these blank and run directly:
```bash
docker compose run --rm ocr-enhancer python /app/main.py
```

---

## Manual File Transfer

If you **manually transfer files** via USB or a file manager (no sync server or Mac app), use this simple mode.

### Quick Start (Manual)

```bash
# 1. Configure your data path in .env.local
echo "SUPERNOTE_DATA_PATH=/path/to/your/supernote/files" >> .env.local

# 2. Run OCR enhancement
docker compose run --rm ocr-enhancer python /app/main.py
```

No database synchronization is needed since there's no sync server to coordinate with.

## Processing State & File Tracking

The SQLite database (`./data/processing.db`) tracks:

- **note_files**: File path, hash, modification time, processing status
- **page_results**: Per-page hash, OCR text, processing time

### When Files Are Reprocessed

Files are **reprocessed** when:
- File hash changes (you added new content)
- Previous processing failed
- File is new (never processed before)

Files are **skipped** when:
- Already successfully processed with same content hash
- This prevents wasting time re-OCRing unchanged files

### Preventing Device Re-OCR

**Problem**: By default, Supernote devices have "Real-time Recognition" enabled (`FILE_RECOGN_TYPE=1` in the .note file header). This causes the device to continuously re-run its own OCR, overwriting any enhanced OCR you inject.

**Solution**: When this tool processes a file, it sets `FILE_RECOGN_TYPE=0` in the notebook header. This disables on-device OCR for that specific file, preserving your enhanced Qwen2.5-VL results.

**Important**: This is a per-file setting. New notebooks created on your device will still have real-time recognition enabled until processed by this tool.

## Performance

### Apple Vision Framework (Default)
- **Speed**: ~0.8 seconds per page average
- **Memory**: ~200MB (minimal footprint)
- **Accuracy**: +41.8% more text vs Supernote device OCR

### Qwen2.5-VL 7B (Optional, requires mlx-vlm)
- **First page**: ~60-120 seconds (MLX kernel compilation)
- **Subsequent pages**: ~20-100 seconds depending on content
- **GPU**: Metal (Apple Silicon) - CPU will appear idle during processing
- **Memory**: ~8GB for 7B model
- **Accuracy**: +107% more text vs Supernote device OCR

See `data/model-comparison-7b-vs-3b.md` for detailed model benchmarks.

## Troubleshooting

### OCR API not available

```bash
# Check if running
curl http://localhost:8100/health

# Check logs if using the provided scripts
tail -f ~/services/ocr-api/logs/server.log
```

### Files keep reprocessing

The file hash is recomputed after OCR injection. If you're seeing files reprocessed, check that the hash update is working:

```bash
sqlite3 ./data/processing.db "SELECT file_path, file_hash, processing_status FROM note_files;"
```

### Bounding boxes in wrong location

OCR coordinates are scaled from the resized image (800px max) to the original (1920x2560). Verify that `ocr_image_width` and `ocr_image_height` are passed correctly.

### Sync conflicts

Always use `./run-with-sync-control.sh` if you have a sync server running.

## Project Structure

```
supernote-ocr-enhancer/
├── .env.example              # Template for local configuration
├── .env.local                # Your local config (git-ignored)
├── Dockerfile                # Container definition
├── docker-compose.yml        # Service configuration
├── run-with-sync-control.sh  # Personal Cloud sync coordination
├── run-with-macapp.sh        # Mac app mode (auto-detects paths)
├── app/
│   ├── main.py               # Entry point and processing loop
│   ├── database.py           # SQLite state tracking
│   ├── ocr_client.py         # OCR API client
│   ├── note_processor.py     # .note file handling
│   └── sync_handlers.py      # Sync database handlers (Mac app & Personal Cloud)
├── examples/
│   └── server.py             # OCR API server (copy to ~/services/ocr-api/)
├── scripts/
│   ├── compare_ocr.py            # OCR comparison tool
│   ├── extract_ocr_text.py       # OCR backup/export
│   ├── test_macapp_single.py     # Test single file with Mac app mode
│   └── cron-macapp-template.sh   # Template for Mac app scheduled OCR
└── data/
    ├── processing.db         # State database (git-ignored)
    └── backups/              # File backups (git-ignored)
```

## License

Apache License 2.0 - See [LICENSE](LICENSE) file.

This means you can use, modify, and distribute this software, but you must:
- Include the original copyright notice
- Provide attribution in derivative works
- State any changes you made

## Acknowledgments

- [supernotelib](https://github.com/jya-dev/supernote-tool) - Supernote .note file parsing
- [ocrmac](https://github.com/straussmaximilian/ocrmac) - Python wrapper for Apple Vision Framework OCR
- [MLX-VLM](https://github.com/Blaizzy/mlx-vlm) - Apple Silicon optimized vision-language models (optional)
- [Qwen2.5-VL](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct) - Alternative OCR model (optional)

## Contributing

Contributions welcome! Please open an issue or PR.
