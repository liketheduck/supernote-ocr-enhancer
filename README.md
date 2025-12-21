# Supernote OCR Enhancer

Docker container that processes Supernote `.note` files using a local MLX-VLM OCR API to replace Supernote's built-in OCR (~27% word error rate) with high-quality Qwen2.5-VL OCR (~5% word error rate).

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Your Mac (Apple Silicon)                    │
│                                                                      │
│  ┌────────────────────────┐      ┌───────────────────────────────┐  │
│  │  supernote-ocr-        │      │  ocr-api (native macOS)       │  │
│  │  enhancer (Docker)     │─────▶│  MLX-VLM + Qwen2.5-VL-7B     │  │
│  │                        │      │  localhost:8100               │  │
│  │  - Extracts pages      │      │                               │  │
│  │  - Tracks state (SQLite)│     │  - GPU-accelerated (Metal)   │  │
│  │  - Injects OCR back    │      │  - Returns text + bboxes     │  │
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

- **High-quality OCR**: Replaces Supernote's ~27% WER with Qwen2.5-VL's ~5% WER
- **Bounding box preservation**: OCR text is positioned correctly in the original document
- **Smart tracking**: SQLite database tracks file hashes to avoid reprocessing unchanged files
- **Backup protection**: Creates timestamped backups before modifying any file
- **Sync server coordination**: Optionally stops Supernote sync server during processing to prevent conflicts
- **Disables device re-OCR**: Sets `FILE_RECOGN_TYPE=0` to prevent device from overwriting enhanced OCR

## Prerequisites

1. **Apple Silicon Mac** (M1/M2/M3/M4) with 16GB+ RAM
2. **Docker Desktop** installed
3. **MLX-VLM OCR API** running locally (see [OCR API Setup](#ocr-api-setup))
4. **Supernote .note files** synced to your Mac

## Quick Start

### 1. Clone and Configure

```bash
git clone https://github.com/yourusername/supernote-ocr-enhancer.git
cd supernote-ocr-enhancer

# Create local configuration
cp .env.example .env.local

# Edit .env.local with your paths
nano .env.local
```

Required settings in `.env.local`:
```bash
# Path to your Supernote data directory
SUPERNOTE_DATA_PATH=/path/to/your/supernote/data

# If using sync server coordination (optional)
SYNC_SERVER_COMPOSE=/path/to/supernote-sync/docker-compose.yml
SYNC_SERVER_ENV=/path/to/supernote-sync/.env
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

The OCR API is a separate service that runs natively on macOS for GPU acceleration.

### Using uv (recommended)

```bash
# Create OCR API directory
mkdir -p ~/services/ocr-api
cd ~/services/ocr-api

# Initialize with uv
uv init --name ocr-api --python 3.11
uv add mlx-vlm pillow fastapi uvicorn python-multipart

# Create server.py (see examples/server.py in this repo)
# Start the server
uv run python server.py
```

The server will:
1. Download the Qwen2.5-VL-7B-Instruct-8bit model (~9GB, first run only)
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

## How It Works

1. **Scan**: Finds all `.note` files in the data directory
2. **Track**: Uses SQLite to track file/page hashes and avoid reprocessing
3. **Extract**: Converts each page to PNG using supernotelib
4. **OCR**: Sends images to MLX-VLM API for text recognition with bounding boxes
5. **Scale**: Converts OCR coordinates from resized image to original dimensions
6. **Inject**: Writes enhanced OCR data into the `.note` file's RECOGNTEXT block
7. **Disable re-OCR**: Sets `FILE_RECOGN_TYPE=0` to prevent device from redoing OCR

## Sync Server Coordination

If you're running a Supernote sync server (for syncing .note files from your device), the `run-with-sync-control.sh` script will:

1. Check if sync server is running
2. Stop it gracefully before OCR processing
3. Run the OCR enhancer
4. Update the sync server's database with new file sizes/hashes
5. Restart the sync server

This prevents file conflicts during sync.

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
├── scripts/
│   ├── compare_ocr.py        # OCR comparison tool
│   ├── extract_ocr_text.py   # OCR backup/export
│   └── test_single_file.py   # Single file testing
└── data/
    ├── processing.db         # State database (git-ignored)
    └── backups/              # File backups (git-ignored)
```

## License

MIT License - See [LICENSE](LICENSE) file.

## Acknowledgments

- [supernotelib](https://github.com/jya-dev/supernote-tool) - Supernote .note file parsing
- [MLX-VLM](https://github.com/Blaizzy/mlx-vlm) - Apple Silicon optimized vision-language models
- [Qwen2.5-VL](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct) - The OCR model

## Contributing

Contributions welcome! Please open an issue or PR.
