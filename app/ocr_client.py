"""
OCR API client for communicating with the MLX-VLM OCR service.
"""

import base64
import io
import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

import requests
from PIL import Image

# Max image dimension - balance between speed and accuracy
# 1280 = high quality, ~60-140s/page
# 800 = faster, ~30-60s/page, still good accuracy for handwriting
MAX_IMAGE_DIMENSION = 800

logger = logging.getLogger(__name__)


def resize_image_if_needed(image_bytes: bytes, max_dim: int = MAX_IMAGE_DIMENSION) -> tuple[bytes, int, int]:
    """
    Resize image if larger than max dimension to avoid GPU OOM.

    Returns:
        Tuple of (resized_bytes, resized_width, resized_height)
    """
    img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size

    if w <= max_dim and h <= max_dim:
        return image_bytes, w, h

    # Calculate new size maintaining aspect ratio
    if w > h:
        new_w = max_dim
        new_h = int(h * max_dim / w)
    else:
        new_h = max_dim
        new_w = int(w * max_dim / h)

    logger.info(f"Resizing image from {w}x{h} to {new_w}x{new_h}")
    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue(), new_w, new_h


@dataclass
class TextBlock:
    """A single text block with bounding box."""
    text: str
    bbox: List[float]  # [left, top, right, bottom] as percentages
    confidence: float
    block_type: str  # "handwriting" or "printed"


@dataclass
class OCRResult:
    """Result from OCR processing."""
    text_blocks: List[TextBlock]
    full_text: str
    processing_time_ms: float
    raw_response: Dict[str, Any]
    ocr_image_width: int = 0   # Width of image sent to OCR (after resize)
    ocr_image_height: int = 0  # Height of image sent to OCR (after resize)


class OCRClient:
    """Client for the MLX-VLM OCR API."""

    def __init__(self, base_url: str = "http://localhost:8100", timeout: int = 180):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()

    def health_check(self) -> bool:
        """Check if OCR API is available and model is loaded."""
        try:
            resp = self.session.get(
                f"{self.base_url}/health",
                timeout=10
            )
            if resp.status_code != 200:
                return False
            data = resp.json()
            return data.get("model_loaded", False)
        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            return False

    def wait_for_ready(self, max_wait: int = 120) -> bool:
        """Wait for the OCR API to be ready."""
        import time
        start = time.time()
        while time.time() - start < max_wait:
            if self.health_check():
                return True
            time.sleep(5)
        return False

    def ocr_image(
        self,
        image_bytes: bytes,
        prompt_type: str = "ocr_with_boxes",
        max_tokens: int = 4096
    ) -> OCRResult:
        """
        Send image to OCR API and get results.

        Args:
            image_bytes: PNG image as bytes
            prompt_type: Type of OCR prompt ("ocr_with_boxes", "ocr_simple", "ocr_layout")
            max_tokens: Maximum tokens in response

        Returns:
            OCRResult with text blocks and bounding boxes

        Raises:
            requests.RequestException: On API errors
            ValueError: On invalid response
        """
        # Resize if needed to avoid GPU OOM
        image_bytes, ocr_width, ocr_height = resize_image_if_needed(image_bytes)
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')

        payload = {
            "image_base64": image_base64,
            "prompt_type": prompt_type,
            "max_tokens": max_tokens,
            "temperature": 0.0
        }

        resp = self.session.post(
            f"{self.base_url}/ocr",
            json=payload,
            timeout=self.timeout
        )
        resp.raise_for_status()

        data = resp.json()
        result = data.get("result", {})

        # Parse text blocks
        text_blocks = []
        raw_blocks = result.get("text_blocks", [])

        for block in raw_blocks:
            text_blocks.append(TextBlock(
                text=block.get("text", ""),
                bbox=block.get("bbox", [0, 0, 100, 100]),
                confidence=block.get("confidence", 0.0),
                block_type=block.get("type", "handwriting")
            ))

        return OCRResult(
            text_blocks=text_blocks,
            full_text=result.get("full_text", ""),
            processing_time_ms=data.get("processing_time_ms", 0),
            raw_response=data,
            ocr_image_width=ocr_width,
            ocr_image_height=ocr_height
        )

    def ocr_image_simple(self, image_bytes: bytes) -> str:
        """
        Simple OCR - just get the text without bounding boxes.

        Args:
            image_bytes: PNG image as bytes

        Returns:
            Extracted text as string
        """
        result = self.ocr_image(image_bytes, prompt_type="ocr_simple")
        return result.full_text
