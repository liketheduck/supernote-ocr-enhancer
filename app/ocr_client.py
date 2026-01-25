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
# None = no resize, process full resolution (slower but best accuracy)
MAX_IMAGE_DIMENSION = None  # Process full resolution images

logger = logging.getLogger(__name__)


def resize_image_if_needed(image_bytes: bytes, max_dim: Optional[int] = MAX_IMAGE_DIMENSION) -> tuple[bytes, int, int]:
    """
    Resize image if larger than max dimension to avoid GPU OOM.

    Returns:
        Tuple of (resized_bytes, resized_width, resized_height)
    """
    img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size

    # If max_dim is None, don't resize - process full resolution
    if max_dim is None:
        logger.info(f"Processing full resolution image: {w}x{h}")
        return image_bytes, w, h

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
            # Check if either Vision Framework or MLX model is available
            vision_available = data.get("vision_available", False)
            mlx_available = data.get("mlx_model_loaded", False)
            return vision_available or mlx_available
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

    def detect_visual_content(self, image_bytes: bytes) -> bool:
        """
        Quick detection of visual content (drawings, diagrams) vs text-only.
        
        Uses a simple prompt to ask if there are drawings/diagrams.
        Very lightweight - just a yes/no question.
        
        Args:
            image_bytes: PNG image as bytes
            
        Returns:
            True if visual content detected, False otherwise
        """
        try:
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            
            payload = {
                "image_base64": image_base64,
                "prompt_type": "visual_detection",
                "max_tokens": 10,  # Very short response
                "temperature": 0.0
            }
            
            resp = self.session.post(
                f"{self.base_url}/ocr",
                json=payload,
                timeout=30  # Quick timeout
            )
            resp.raise_for_status()
            
            data = resp.json()
            result = data.get("result", {})
            response_text = result.get("full_text", "").lower()
            
            # Simple detection - look for keywords indicating visual content
            visual_keywords = ["yes", "drawing", "diagram", "sketch", "image", "picture", "chart", "graph"]
            has_visual = any(keyword in response_text for keyword in visual_keywords)
            
            if has_visual:
                logger.debug("Visual content detected in image")
            
            return has_visual
            
        except Exception as e:
            logger.debug(f"Visual detection failed: {e}")
            return False  # Fail silently - don't break OCR flow

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

    def ocr_image_vision(self, image_bytes: bytes) -> OCRResult:
        """
        OCR using Apple Vision Framework with word-level bounding boxes.

        This provides accurate word-level bounding boxes for search highlighting.

        Args:
            image_bytes: PNG image as bytes

        Returns:
            OCRResult with word-level text blocks and bounding boxes

        Raises:
            requests.RequestException: On API errors
            ValueError: On invalid response
        """
        # DO NOT resize for Vision Framework - it needs full resolution for accurate bboxes
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')

        # Get original image dimensions
        img = Image.open(io.BytesIO(image_bytes))
        orig_width, orig_height = img.size

        payload = {
            "image_base64": image_base64,
            "prompt_type": "vision_ocr",  # Not used by vision endpoint but required
            "max_tokens": 4096,
            "temperature": 0.0
        }

        resp = self.session.post(
            f"{self.base_url}/ocr/vision",
            json=payload,
            timeout=self.timeout
        )
        resp.raise_for_status()

        data = resp.json()
        result = data.get("result", {})

        # Parse text blocks from Vision Framework
        text_blocks = []
        raw_blocks = result.get("text_blocks", [])

        for block in raw_blocks:
            # Vision returns bbox in pixels [left, top, right, bottom]
            # We keep them as-is since they're already in pixels
            text_blocks.append(TextBlock(
                text=block.get("text", ""),
                bbox=block.get("bbox", [0, 0, 0, 0]),
                confidence=block.get("confidence", 0.0),
                block_type="vision_ocr"
            ))

        return OCRResult(
            text_blocks=text_blocks,
            full_text=result.get("full_text", ""),
            processing_time_ms=data.get("processing_time_ms", 0),
            raw_response=data,
            ocr_image_width=orig_width,
            ocr_image_height=orig_height
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

    def generate_text(self, prompt: str, max_tokens: int = 500, temperature: float = 0.3) -> str:
        """
        Generate text using Qwen LLM (no image, text-only).
        
        Useful for:
        - Summarizing OCR text
        - Cleaning up OCR errors
        - Extracting information
        
        Args:
            prompt: Text prompt for generation
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 = deterministic, 1.0 = creative)
            
        Returns:
            Generated text
            
        Raises:
            requests.RequestException: On API errors
            ValueError: If model not loaded
        """
        payload = {
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        
        resp = self.session.post(
            f"{self.base_url}/generate",
            json=payload,
            timeout=self.timeout
        )
        
        if resp.status_code == 503:
            raise ValueError("Qwen model not loaded. Start OCR API with OCR_MODEL_PATH environment variable.")
        
        resp.raise_for_status()
        data = resp.json()
        return data.get("text", "")
