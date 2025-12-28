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
- **Line break preservation**: Detects line structure from Y-coordinates, maintains paragraph formatting
- **Smart tracking**: SQLite database tracks file hashes to avoid reprocessing unchanged files
- **Backup protection**: Creates timestamped backups before modifying any file
- **Live sync server support**: Updates sync database while server runs (no restart needed)
- **Proper coordinate system**: Uses device's native coordinate system (PNG pixels ÷ 11.9) for perfect highlighting
- **Search-enabled**: TYPE='1' configuration allows device to search injected OCR text

## Performance

**Production test results** (100+ files, 300+ pages):
- **Processing time**: ~4 minutes total
- **Speed**: ~0.8 seconds per page average
- **Success rate**: 96%+
- **Accuracy**: +40% more text captured vs Supernote device OCR
- **vs Qwen2.5-VL 7B**: 150x faster (optimal trade-off for batch processing)

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
```

**Optional** - Only if using a self-hosted Supernote Cloud sync server:
```bash
# Enable Personal Cloud mode and provide MySQL password
STORAGE_MODE=personal_cloud
MYSQL_PASSWORD=your_mysql_password  # Get with: docker exec supernote-mariadb env | grep MYSQL_PASSWORD
```

> **Note**: If you don't use a sync server (manual file transfer or Mac app), leave these settings out.

### 2. Build the Container

```bash
docker compose build
```

### 3. Start the OCR API

You need the OCR API server running locally. See [OCR API Setup](#ocr-api-setup) below.

### 4. Run OCR Enhancement

```bash
docker compose run --rm ocr-enhancer python /app/main.py
```

This works with or without a sync server running. The OCR enhancer:
- Skips files that haven't changed (fast no-op when nothing to process)
- Updates the sync database atomically while the server runs
- Bumps file timestamps by 1 second so your OCR'd files win the next sync

> **Note**: The sync server does NOT need to be stopped. MariaDB handles concurrent access safely, and the sync protocol is stateless. See [Architecture: Why No Server Restart?](#architecture-why-no-server-restart) for details.

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

### Keeping the OCR API Running

The OCR API must be running for the enhancer to work. Choose one of these options:

#### Option 1: Always-On (Recommended)

Install as a macOS LaunchAgent that starts automatically on login and restarts if it crashes:

```bash
./scripts/install-launchd.sh
```

This is the recommended approach because:
- **Zero maintenance**: Starts automatically, restarts on crash
- **Always ready**: Hourly cron jobs will always find the API available
- **Low overhead**: ~50-100MB RAM when idle, 0% CPU

To remove:
```bash
./scripts/install-launchd.sh --remove
```

#### Option 2: Manual Start

Start the OCR API manually when you need it:

```bash
./scripts/start-ocr-api.sh
```

This runs in the foreground (Ctrl+C to stop). Use this if you prefer manual control or want to save the ~50MB RAM when not processing.

#### Checking Status

```bash
# Check if OCR API is running
./scripts/start-ocr-api.sh --check

# Or directly
curl http://localhost:8100/health
```

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
| `FILE_RECOGN_TYPE` | `0` | `0`=no device OCR, `1`=device OCR on, `keep`=preserve |

## How It Works

1. **Scan**: Finds all `.note` files in the data directory
2. **Track**: Uses SQLite to track file/page hashes and avoid reprocessing
3. **Extract**: Converts each page to PNG (1920x2560) using supernotelib
4. **OCR**: Sends full-resolution images to Apple Vision Framework via OCR API for word-level text recognition with pixel-accurate bounding boxes
5. **Transform**: Converts Vision Framework coordinates (PNG pixels) to Supernote's coordinate system (PNG pixels ÷ 11.9)
6. **Inject**: Writes enhanced OCR data into the `.note` file's RECOGNTEXT block with proper coordinate format
7. **Configure device**: Sets `FILE_RECOGN_TYPE` (default `0`) and `FILE_RECOGN_LANGUAGE=en_US` for search compatibility

### FILE_RECOGN_TYPE: What It Actually Controls

`FILE_RECOGN_TYPE` controls **realtime recognition during writing**, NOT search capability:

| Setting | Device OCRs While Writing? | Search Works? | Description |
|---------|---------------------------|---------------|-------------|
| `0` | ❌ No | ✅ Yes (if OCR data exists) | **Default** - Preserves our Vision OCR |
| `1` | ✅ Yes (realtime OCR) | ✅ Yes | Device OCRs new strokes as you write |
| `keep` | (unchanged) | ✅ Yes | Preserves whatever the file had before |

**Key insight**: Files with TYPE='0' are still fully searchable if they have RECOGNTEXT data. The TYPE setting only controls whether the device does realtime OCR while you're writing - it doesn't affect search.

**Why we use TYPE='0' (default):**
- Prevents device from overwriting our high-quality Vision OCR
- Search still works perfectly (RECOGNTEXT data is preserved)
- Reduces unnecessary processing on the device

**The workflow:**
1. You write on device → no realtime OCR (TYPE='0')
2. File syncs to server → our enhancer applies Vision OCR
3. File syncs back to device → device uses our OCR for search
4. New edits sync → we OCR them on next hourly run

**To enable device OCR** (if you want realtime recognition while writing):
```bash
# In .env.local
FILE_RECOGN_TYPE=1
```

**Testing notes**:
- `LANG='none'` causes "redownload language" prompt (never use)
- `RECOGNSTATUS=1` (done) doesn't prevent device re-OCR on edits - TYPE controls realtime behavior

### Architecture: Why No Server Restart?

Previous versions stopped the sync server during OCR processing. This is no longer necessary because:

**1. MariaDB handles concurrent access safely**
- Row-level locking prevents simultaneous writes to the same record
- ACID transactions ensure data consistency
- Our UPDATE statements are single-row atomic operations

**2. The sync protocol is stateless**
- Each device sync is a fresh request-response cycle
- No long-running transactions span multiple requests
- Updated database values are seen immediately on next sync

**3. File-level sync uses terminal_file_edit_time**
- We update `size`, `md5`, and bump `terminal_file_edit_time` by +1 second
- Sync protocol: higher `terminal_file_edit_time` wins (determines upload vs download)
- If user hasn't edited: our +1s bump > device's timestamp → device downloads our OCR
- If user HAS edited: their new timestamp >> our +1s bump → device uploads (user wins)
- This prevents conflicts: there's always a clear winner based on timestamp comparison

**4. Graceful no-op for unchanged files**
- SQLite tracks file hashes locally
- Files that haven't changed are skipped in milliseconds
- Running hourly adds negligible overhead

**5. Age threshold prevents mid-sync processing**
- Files modified less than 60 seconds ago are skipped
- Ensures sync completes before OCR runs

This architecture allows hourly OCR runs without service interruption or database corruption risk.

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

If you use a **self-hosted Supernote Cloud sync server** (like [Supernote-Private-Cloud](https://github.com/nickian/Supernote-Private-Cloud)), this mode works seamlessly. The OCR enhancer updates the sync database while the server runs - no restart needed.

### Do I need special configuration?

- **If you manually transfer files** (USB, file manager): No sync server needed. Just point `SUPERNOTE_DATA_PATH` to your .note files.
- **If you use the Mac app**: See [Supernote Mac App](#supernote-mac-app) section above.
- **If you use a self-hosted sync server**: Just run the OCR enhancer - it updates the database automatically.

### How It Works

When OCR modifies a .note file, the enhancer updates the sync server's MariaDB database:
- Sets new `size` and `md5` hash
- Bumps `terminal_file_edit_time` by +1 second (so server version is "newer")
- Updates `update_time` to current time

This happens atomically via Docker socket access to the MariaDB container. The bumped timestamp makes the server's version win the sync (device downloads), unless the user has edited on the device (their timestamp would be much later, so device uploads).

### Configuration

Configure in `.env.local`:
```bash
# Enable Personal Cloud sync mode
STORAGE_MODE=personal_cloud

# MySQL password from your sync server's MariaDB container
# Find it with: docker exec supernote-mariadb env | grep MYSQL_PASSWORD
MYSQL_PASSWORD=your_mysql_password_here
```

### Scheduling Personal Cloud OCR (Container Cron)

The container runs cron jobs automatically:

| Schedule | Behavior |
|----------|----------|
| Every hour (:00) | Skips files uploaded in last 8 hours (conflict prevention) |
| **3:30 AM** | **Full run** - processes ALL files regardless of upload time |

The 3:30am run is low-risk for conflicts since you're likely asleep and not editing.

Additional safeguards:
- **Age threshold**: Files modified <60 seconds ago are skipped (prevents processing mid-sync)
- **Hash comparison**: Already-processed files are skipped in milliseconds
- **Atomic updates**: Database updates are safe while sync server runs

To use container-based cron:
```bash
# Start the container (runs cron daemon)
docker compose up -d

# View logs
docker compose logs -f ocr-enhancer
```

The cron schedule is in `config/crontab` (default: every hour at :00).

### Legacy: Manual Sync Control

The `run-with-sync-control.sh` script is still available for manual runs with explicit sync server control:

```bash
./run-with-sync-control.sh           # Stops server, runs OCR, restarts server
./run-with-sync-control.sh --dry-run # Preview what would happen
```

This is no longer required but may be preferred for initial testing.

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

### Device Re-OCR Behavior

**Background**: Supernote devices have "Real-time Recognition" controlled by `FILE_RECOGN_TYPE` in the .note file header. This setting controls whether the device performs OCR while you write.

**Our approach**: We set `FILE_RECOGN_TYPE=0` by default to preserve our high-quality Vision OCR:
- ✅ Search and highlighting work for all OCR text
- ✅ Device won't overwrite our OCR with lower-quality realtime OCR
- ✅ New edits are OCR'd by our enhancer on the next hourly sync

**Alternative**: Set `FILE_RECOGN_TYPE=1` in `.env.local` if you want the device to do realtime OCR as you write. This gives immediate (but lower quality) searchability for new strokes, which our enhancer will improve on next sync.

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
- **Accuracy**: Higher accuracy than Vision Framework, but much slower

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

Vision Framework OCR uses full-resolution images (1920x2560) and returns pixel coordinates that are then divided by 11.9 for Supernote's coordinate system. If highlighting is misaligned, verify the coordinate transformation in `note_processor.py`.

### Sync conflicts

**Why conflicts occur:**

The Supernote sync protocol creates a CONFLICT when both sides have changes:
```
1. Device uploads file (md5=A)
2. We run OCR → server now has md5=B
3. User edits on device → device now has md5=C
4. Device syncs → Server sees: device changed (A→C) AND server changed (A→B)
5. Both sides changed → CONFLICT (to protect user's work)
```

**Why timestamps alone can't fix this:**

We bump `terminal_file_edit_time` by +1 second so server wins when only server changed. But if the user edited on device, their timestamp is hours/days later than our +1 second bump. The sync protocol sees both sides have changes and creates a conflict to prevent data loss.

We could force server to always win (set timestamp to year 2099), but that would **overwrite user's handwriting** - unacceptable.

**Our solution - skip actively-edited files:**

1. **Skip recently uploaded files**: Files uploaded in the last 8 hours are skipped during hourly runs
2. **3:30am full run**: Processes ALL files regardless of upload time (low conflict risk)
3. **Then OCR**: Device's local file is "clean" (no pending edits), only server changed
4. **Device downloads**: No conflict because only one side changed

**If you still see conflicts:**
- You edited the file on device after OCR ran but before syncing
- The 3:30am run should catch most files safely
- The conflict file contains our OCR version - you can delete it or keep for reference

**Configuration checks:**
1. Verify `STORAGE_MODE=personal_cloud` is set in `.env.local`
2. Verify `MYSQL_PASSWORD` matches your MariaDB container's password
3. Check MariaDB is accessible: `docker exec supernote-mariadb mysqladmin ping`

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
├── config/
│   ├── crontab               # Cron schedule for Docker container
│   └── com.supernote.ocr-api.plist.template  # LaunchAgent template
├── examples/
│   └── server.py             # OCR API server (copy to ~/services/ocr-api/)
├── scripts/
│   ├── cron-ocr-job.sh           # Cron job script (runs inside Docker)
│   ├── cron-macapp-template.sh   # Template for Mac app scheduled OCR (runs on host)
│   ├── install-launchd.sh        # Install OCR API as LaunchAgent (always-on)
│   ├── start-ocr-api.sh          # Start OCR API manually (foreground)
│   ├── compare_ocr.py            # OCR comparison tool
│   └── extract_ocr_text.py       # OCR backup/export
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
