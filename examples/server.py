#!/usr/bin/env python3
"""
MLX-VLM OCR API Server
Provides API for handwriting OCR with bounding boxes.
Optimized for Apple Silicon (M1/M2/M3/M4).

Usage:
    # 7B model (better accuracy, ~8GB RAM, ~60-120s/page)
    OCR_MODEL_PATH=mlx-community/Qwen2.5-VL-7B-Instruct-8bit uv run python server.py

    # 3B model (faster, ~4GB RAM, ~20-40s/page)
    OCR_MODEL_PATH=mlx-community/Qwen2.5-VL-3B-Instruct-8bit uv run python server.py
"""

import os
import sys
import json
import base64
import logging
import time
from io import BytesIO
from pathlib import Path
from typing import Optional, Any
from contextlib import asynccontextmanager

import mlx.core as mx
from mlx_vlm import load, generate
from mlx_vlm.prompt_utils import apply_chat_template
from mlx_vlm.utils import load_config
from PIL import Image
from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Configuration via environment variables
MODEL_PATH = os.getenv("OCR_MODEL_PATH", "mlx-community/Qwen2.5-VL-7B-Instruct-8bit")
HOST = os.getenv("OCR_HOST", "0.0.0.0")
PORT = int(os.getenv("OCR_PORT", "8100"))
MAX_TOKENS = int(os.getenv("OCR_MAX_TOKENS", "4096"))
LOG_LEVEL = os.getenv("OCR_LOG_LEVEL", "INFO")

# Setup logging
log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_dir / 'server.log')
    ]
)
logger = logging.getLogger("ocr-api")

# Global model reference
model = None
processor = None
config = None


# Prompts optimized for handwriting OCR with bounding boxes
PROMPTS = {
    "ocr_with_boxes": """You are an OCR engine, not a writing assistant.

Task:
- Read ALL handwritten and printed text from this image.
- For each text element, provide the bounding box coordinates.
- PRESERVE formatting exactly as written:
  - Line breaks between lines
  - Paragraph breaks (blank lines)
  - Indentation (use spaces)
  - Bullet points (-, *, •)
  - Numbered lists (1., 2., etc.)
- Output as JSON with this exact structure:

{
  "text_blocks": [
    {
      "text": "the transcribed text for this line",
      "bbox": [x1, y1, x2, y2],
      "confidence": 0.95,
      "type": "handwriting" or "printed"
    }
  ],
  "full_text": "all text preserving original formatting with \\n for line breaks"
}

Critical constraints:
- Each distinct line should be a separate text_block
- Preserve indentation and list markers in the text
- bbox coordinates are [left, top, right, bottom] as percentages (0-100) of image dimensions
- Do NOT explain, analyze, or add commentary
- Output ONLY valid JSON""",

    "ocr_simple": """You are an OCR engine, not a writing assistant.

Task:
- Read the handwritten note in the image.
- Output the exact transcription of the text as plain markdown.

Critical constraints:
- Do NOT explain what you are doing.
- Do NOT think step-by-step.
- Do NOT describe, analyze, or comment on the note.
- Do NOT repeat any single word more than twice in a row.
- Your entire response must be ONLY the final transcription text, nothing else.""",

    "ocr_layout": """Extract all text from this document image.
Return a JSON object with:
- "blocks": array of text blocks, each with "text", "bbox" [x1,y1,x2,y2] as percentages, and "type" (heading/paragraph/list/handwriting)
- "reading_order": array of block indices in reading order
- "full_text": concatenated text in reading order

Output ONLY valid JSON, no explanation."""
}


class OCRRequest(BaseModel):
    """Request model for OCR endpoint"""
    image_base64: Optional[str] = None
    image_url: Optional[str] = None
    prompt_type: str = "ocr_with_boxes"
    custom_prompt: Optional[str] = None
    max_tokens: int = MAX_TOKENS
    temperature: float = 0.0


class OCRResponse(BaseModel):
    """Response model for OCR endpoint"""
    result: Any
    processing_time_ms: float
    model: str
    prompt_type: str


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    model_loaded: bool
    model_name: str
    uptime_seconds: float


# Track server start time
start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup, cleanup on shutdown"""
    global model, processor, config

    logger.info(f"Loading model: {MODEL_PATH}")
    load_start = time.time()

    try:
        model, processor = load(MODEL_PATH)
        config = load_config(MODEL_PATH)
        load_time = time.time() - load_start
        logger.info(f"Model loaded successfully in {load_time:.2f}s")
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        raise

    yield

    # Cleanup
    logger.info("Shutting down OCR API server")
    del model
    del processor
    mx.metal.clear_cache()


app = FastAPI(
    title="MLX-VLM OCR API",
    description="Handwriting OCR with bounding boxes using Qwen2.5-VL on Apple Silicon",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for access from other services
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def decode_image(image_base64: Optional[str] = None, image_url: Optional[str] = None) -> Image.Image:
    """Decode image from base64 or URL"""
    if image_base64:
        image_data = base64.b64decode(image_base64)
        return Image.open(BytesIO(image_data)).convert("RGB")
    elif image_url:
        import urllib.request
        with urllib.request.urlopen(image_url) as response:
            image_data = response.read()
        return Image.open(BytesIO(image_data)).convert("RGB")
    else:
        raise ValueError("Either image_base64 or image_url must be provided")


def run_ocr(image: Image.Image, prompt: str, max_tokens: int, temperature: float) -> str:
    """Run OCR inference on image"""
    global model, processor, config

    # Apply chat template
    formatted_prompt = apply_chat_template(
        processor,
        config,
        prompt,
        num_images=1
    )

    # Generate
    output = generate(
        model,
        processor,
        formatted_prompt,
        [image],
        max_tokens=max_tokens,
        temperature=temperature,
        verbose=False
    )

    # Extract text from GenerationResult if needed
    if hasattr(output, 'text'):
        return output.text
    elif hasattr(output, '__str__'):
        return str(output)
    return output


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy" if model is not None else "unhealthy",
        model_loaded=model is not None,
        model_name=MODEL_PATH,
        uptime_seconds=time.time() - start_time
    )


@app.post("/ocr", response_model=OCRResponse)
async def ocr_endpoint(request: OCRRequest):
    """
    Perform OCR on an image.

    Args:
        request: OCRRequest with image (base64 or URL) and prompt configuration

    Returns:
        OCRResponse with extracted text and bounding boxes
    """
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    start = time.time()

    try:
        # Decode image
        image = decode_image(request.image_base64, request.image_url)
        logger.info(f"Processing image: {image.size[0]}x{image.size[1]}")

        # Get prompt
        if request.custom_prompt:
            prompt = request.custom_prompt
        elif request.prompt_type in PROMPTS:
            prompt = PROMPTS[request.prompt_type]
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown prompt_type: {request.prompt_type}. Available: {list(PROMPTS.keys())}"
            )

        # Run OCR
        result_text = run_ocr(image, prompt, request.max_tokens, request.temperature)

        # Try to parse as JSON if expected
        if request.prompt_type in ["ocr_with_boxes", "ocr_layout"]:
            try:
                # Clean up response - remove markdown code blocks if present
                cleaned = result_text.strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                if cleaned.startswith("```"):
                    cleaned = cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                result = json.loads(cleaned.strip())
            except json.JSONDecodeError:
                # Return raw text if JSON parsing fails
                result = {"raw_text": result_text, "parse_error": "Could not parse as JSON"}
        else:
            result = {"text": result_text}

        processing_time = (time.time() - start) * 1000
        logger.info(f"OCR completed in {processing_time:.2f}ms")

        return OCRResponse(
            result=result,
            processing_time_ms=processing_time,
            model=MODEL_PATH,
            prompt_type=request.prompt_type
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("OCR processing failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ocr/upload")
async def ocr_upload(
    file: UploadFile = File(...),
    prompt_type: str = Form(default="ocr_with_boxes"),
    max_tokens: int = Form(default=MAX_TOKENS)
):
    """
    OCR endpoint that accepts file upload directly.
    Useful for testing and simple integrations.
    """
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    start = time.time()

    try:
        # Read and decode image
        contents = await file.read()
        image = Image.open(BytesIO(contents)).convert("RGB")
        logger.info(f"Processing uploaded image: {file.filename}, {image.size[0]}x{image.size[1]}")

        # Get prompt
        prompt = PROMPTS.get(prompt_type, PROMPTS["ocr_with_boxes"])

        # Run OCR
        result_text = run_ocr(image, prompt, max_tokens, 0.0)

        # Try to parse as JSON
        try:
            cleaned = result_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            result = json.loads(cleaned.strip())
        except json.JSONDecodeError:
            result = {"raw_text": result_text}

        processing_time = (time.time() - start) * 1000

        return {
            "result": result,
            "processing_time_ms": processing_time,
            "filename": file.filename
        }

    except Exception as e:
        logger.exception("OCR upload processing failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/prompts")
async def list_prompts():
    """List available prompt types"""
    return {
        "available_prompts": list(PROMPTS.keys()),
        "descriptions": {
            "ocr_with_boxes": "Full OCR with bounding boxes as JSON (recommended for Supernote)",
            "ocr_simple": "Simple text extraction, markdown output",
            "ocr_layout": "Layout-aware OCR with reading order"
        }
    }


if __name__ == "__main__":
    logger.info(f"Starting OCR API server on {HOST}:{PORT}")
    logger.info(f"Using model: {MODEL_PATH}")
    uvicorn.run(
        "server:app",
        host=HOST,
        port=PORT,
        log_level=LOG_LEVEL.lower(),
        reload=False  # Disable reload in production for stability
    )
