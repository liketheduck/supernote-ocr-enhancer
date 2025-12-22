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

- **High-quality OCR**: Replaces Supernote's ~27% WER with Apple Vision Framework's ~5% WER
- **Accurate bounding boxes**: Word-level bounding boxes enable search highlighting on device
- **Smart tracking**: SQLite database tracks file hashes to avoid reprocessing unchanged files
- **Backup protection**: Creates timestamped backups before modifying any file
- **Sync server coordination**: Optionally stops Supernote sync server during processing to prevent conflicts
- **Proper coordinate system**: Uses device's native coordinate system (PNG pixels ÷ 11.9) for perfect highlighting

## Prerequisites

1. **Apple Silicon Mac** (M1/M2/M3/M4) with 16GB+ RAM
2. **Docker Desktop** installed
3. **MLX-VLM OCR API** running locally (see [OCR API Setup](#ocr-api-setup))
4. **Supernote .note files** synced to your Mac

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

**Simple run** (process all files once):
```bash
docker compose run --rm supernote-ocr-enhancer
```

**With sync server coordination** (recommended if using Supernote sync):
```bash
./run-with-sync-control.sh
```

**Dry run** (see what would happen):
```bash
./run-with-sync-control.sh --dry-run
```

## OCR API Setup

The OCR API is a separate service that runs **natively on macOS** (not in Docker) to leverage Metal GPU acceleration. You must set this up before running the enhancer.

### Using uv (recommended)

```bash
# Create OCR API directory
mkdir -p ~/services/ocr-api
cd ~/services/ocr-api

# Initialize with uv
uv init --name ocr-api --python 3.11
uv add mlx-vlm pillow fastapi uvicorn python-multipart

# Copy server.py from this repo
cp /path/to/supernote-ocr-enhancer/examples/server.py .

# Start with 7B model (recommended - better accuracy)
uv run python server.py

# OR start with 3B model (faster, less RAM)
OCR_MODEL_PATH=mlx-community/Qwen2.5-VL-3B-Instruct-8bit uv run python server.py
```

### Model Selection: 7B vs 3B

Both models dramatically improve on Supernote's built-in OCR (~27% word error rate):

| Model | RAM | Speed | Accuracy | Improvement over Supernote |
|-------|-----|-------|----------|----------------------------|
| **7B** (default) | ~8GB | ~60-120s/page | ~5% WER | **5x better** |
| **3B** | ~4GB | ~20-40s/page | ~8-10% WER | ~3x better |

**Recommendation**: Use **7B** unless you're RAM-constrained or batch-processing hundreds of pages. The 3B model is faster but makes more errors on messy handwriting, abbreviations, and edge cases.

Set via environment variable:
```bash
# 7B model (default)
export OCR_MODEL_PATH=mlx-community/Qwen2.5-VL-7B-Instruct-8bit

# 3B model (faster)
export OCR_MODEL_PATH=mlx-community/Qwen2.5-VL-3B-Instruct-8bit
```

The server will:
1. Download the selected model (first run only: ~9GB for 7B, ~4GB for 3B)
2. Start listening on `http://localhost:8100`
3. Provide `/ocr` endpoint for image OCR with bounding boxes

### Health Check

```bash
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

## How It Works

1. **Scan**: Finds all `.note` files in the data directory
2. **Track**: Uses SQLite to track file/page hashes and avoid reprocessing
3. **Extract**: Converts each page to PNG (1920x2560) using supernotelib
4. **OCR**: Sends full-resolution images to Apple Vision Framework via OCR API for word-level text recognition with pixel-accurate bounding boxes
5. **Transform**: Converts Vision Framework coordinates (PNG pixels) to Supernote's coordinate system (PNG pixels ÷ 11.9)
6. **Inject**: Writes enhanced OCR data into the `.note` file's RECOGNTEXT block with proper coordinate format
7. **Enable highlighting**: Sets `FILE_RECOGN_TYPE=1` and `FILE_RECOGN_LANGUAGE=en_US` so device uses OCR for search highlighting

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

## Supernote Cloud / Sync Server

### Do I need this?

- **If you manually transfer files** (USB, file manager): You don't need a sync server. Just point `SUPERNOTE_DATA_PATH` to your .note files.
- **If you use Supernote Cloud sync**: You need to coordinate with it to prevent conflicts.

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
docker compose run --rm supernote-ocr-enhancer
```

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

- **First page**: ~60-120 seconds (MLX kernel compilation)
- **Subsequent pages**: ~20-100 seconds depending on content
- **GPU**: Metal (Apple Silicon) - CPU will appear idle during processing
- **Memory**: ~8GB for 7B model + image processing

See `data/model-comparison-7b-vs-3b.md` for 7B vs 3B model benchmarks.

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
├── run-with-sync-control.sh  # Sync coordination wrapper
├── app/
│   ├── main.py               # Entry point and processing loop
│   ├── database.py           # SQLite state tracking
│   ├── ocr_client.py         # OCR API client
│   └── note_processor.py     # .note file handling
├── examples/
│   └── server.py             # OCR API server (copy to ~/services/ocr-api/)
├── scripts/
│   ├── compare_ocr.py        # OCR comparison tool
│   └── extract_ocr_text.py   # OCR backup/export
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
- [MLX-VLM](https://github.com/Blaizzy/mlx-vlm) - Apple Silicon optimized vision-language models
- [Qwen2.5-VL](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct) - The OCR model

## Contributing

Contributions welcome! Please open an issue or PR.
