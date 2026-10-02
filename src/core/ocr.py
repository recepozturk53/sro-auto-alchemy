"""
OCR module for parsing game log text using OpenCV + Tesseract.
Implements thresholding preprocessing and strict regex parsing.
"""

import os
import re
import shutil
import cv2
import numpy as np
import pytesseract
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass
from PIL import Image
import threading


def _tesseract_path_candidates() -> Tuple[str, ...]:
    """
    Well-known Windows locations of tesseract.exe, plus the TESSERACT_CMD override.

    Returns:
        Ordered tuple of candidate paths (may contain empty strings)
    """
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    return (
        os.environ.get("TESSERACT_CMD", ""),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.join(local_appdata, "Programs", "Tesseract-OCR", "tesseract.exe"),
        os.path.join(local_appdata, "Tesseract-OCR", "tesseract.exe"),
    )


def locate_tesseract() -> Tuple[bool, str]:
    """
    Point pytesseract at a working tesseract.exe and verify that it runs.

    Tries the PATH lookup first (pytesseract default), then the common install
    directories and the TESSERACT_CMD environment variable. Verifying with
    get_tesseract_version() means a broken or missing binary is reported as
    unavailable instead of failing silently on every OCR call.

    Returns:
        Tuple of (available, detail) where detail is the detected version string
        or the last error message
    """
    last_error = ""

    # 1. Default: pytesseract resolves "tesseract" from PATH.
    try:
        return True, str(pytesseract.get_tesseract_version())
    except Exception as exc:
        last_error = str(exc)

    # 2. Known / explicit install locations.
    for candidate in _tesseract_path_candidates():
        if not candidate or not os.path.isfile(candidate):
            continue
        pytesseract.pytesseract.tesseract_cmd = candidate
        try:
            return True, str(pytesseract.get_tesseract_version())
        except Exception as exc:
            last_error = str(exc)

    # 3. Last resort: whatever shutil.which() can find.
    found = shutil.which("tesseract")
    if found:
        pytesseract.pytesseract.tesseract_cmd = found
        try:
            return True, str(pytesseract.get_tesseract_version())
        except Exception as exc:
            last_error = str(exc)

    return False, last_error


@dataclass
class ParseResult:
    """Result of parsing game log."""
    success: bool
    result_type: str  # "plus", "stat", "failed", "unknown"
    value: Optional[Any] = None
    raw_text: str = ""
    error: Optional[str] = None


class OCRProcessor:
    """
    OCR processor for game log parsing.
    Uses OpenCV thresholding + Tesseract with strict regex patterns.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    # Regex patterns for parsing game log
    # Plus patterns: +1, +2, etc. also handles "Item +5" format
    PLUS_PATTERN = re.compile(r'\+\s*(\d+)', re.IGNORECASE)
    PLUS_ALT_PATTERN = re.compile(r'plus\s*(\d+)|item\s*\+\s*(\d+)', re.IGNORECASE)
    FAILED_PATTERN = re.compile(r'failed|fail|error|unsuccessful', re.IGNORECASE)
    SUCCESS_PATTERN = re.compile(r'success|succeeded', re.IGNORECASE)
    
    # Stat patterns: [12.2->12.4] or [(82.9%~98.6%) -> (81.6%~97.1%)]
    # Also handles variations with spaces and different brackets
    STAT_SIMPLE_PATTERN = re.compile(r'\[\s*([\d.]+)\s*[-~>]+\s*([\d.]+)\s*\]', re.IGNORECASE)
    STAT_RANGE_PATTERN = re.compile(r'\[\s*\(?\s*([\d.]+)\s*%?\s*~\s*([\d.]+)\s*%?\s*\)?\s*[-~>]+\s*\(?\s*([\d.]+)\s*%?\s*~\s*([\d.]+)\s*%?\s*\)?\s*\]', re.IGNORECASE)
    STAT_ARROW_PATTERN = re.compile(r'([\d.]+)\s*->\s*([\d.]+)', re.IGNORECASE)
    
    # SRO specific patterns: "beenchangedto(297->301]" or similar
    STAT_CHANGEDTO_PATTERN = re.compile(r'changedto\s*\(?[\s]*(\d+)\s*[-~>]+\s*(\d+)', re.IGNORECASE)
    STAT_PARENS_PATTERN = re.compile(r'\(\s*(\d+)\s*[-~>]+\s*(\d+)\s*\]', re.IGNORECASE)
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._ocr_lock = threading.RLock()
            # Locate and verify the Tesseract engine once at startup.
            self._tesseract_available, self._tesseract_detail = locate_tesseract()
            self._initialized = True

    @property
    def is_tesseract_available(self) -> bool:
        """Whether a working Tesseract engine was detected."""
        return self._tesseract_available

    def tesseract_info(self) -> str:
        """Human-readable Tesseract status (version string or error message)."""
        return self._tesseract_detail
    
    def preprocess_image(self, image: np.ndarray, threshold: int = 150) -> np.ndarray:
        """
        Preprocess image for OCR using OpenCV thresholding.
        
        Args:
            image: BGR numpy array
            threshold: Fallback threshold value (ignored while Otsu is active)
            
        Returns:
            Preprocessed grayscale image
        """
        with self._ocr_lock:
            # Convert to grayscale
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            # Upscale small crops: Tesseract recognises glyphs much better when
            # they are not tiny.
            if gray.shape[0] < 200:
                gray = cv2.resize(
                    gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC
                )
            
            # Apply Gaussian blur to reduce noise
            blurred = cv2.GaussianBlur(gray, (3, 3), 0)
            
            # Binarize with Otsu's method. The fixed threshold value is only a
            # fallback: OpenCV ignores it while THRESH_OTSU is active.
            _, thresh = cv2.threshold(
                blurred, 
                threshold, 
                255, 
                cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
            
            # Game logs are light text on a dark background, but Tesseract
            # expects dark text on a light background - invert when needed.
            if float(np.mean(thresh)) < 127.0:
                thresh = cv2.bitwise_not(thresh)

            # Apply morphological operations to clean up text
            kernel = np.ones((2, 2), np.uint8)
            cleaned = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
            
            return cleaned
    
    def extract_text(self, image: np.ndarray, psm: int = 6, threshold: int = 150) -> str:
        """
        Extract text from image using Tesseract OCR.
        
        Args:
            image: BGR numpy array
            psm: Tesseract page segmentation mode (default 6)
            threshold: Threshold for preprocessing
            
        Returns:
            Extracted text string
        """
        with self._ocr_lock:
            # Retry locating Tesseract; the engine may have been installed while
            # the application was already running.
            if not self._tesseract_available:
                self._tesseract_available, self._tesseract_detail = locate_tesseract()
            if not self._tesseract_available:
                print(
                    "OCR Error: Tesseract engine not found "
                    f"({self._tesseract_detail}). Install Tesseract or set TESSERACT_CMD."
                )
                return ""

            try:
                # Preprocess the image
                processed = self.preprocess_image(image, threshold)
                
                # Configure Tesseract
                config = f'--psm {psm} --oem 3 -c tessedit_char_whitelist=0123456789+-.>%~[]()abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ '
                
                # Run OCR
                text = pytesseract.image_to_string(processed, config=config)
                
                return text.strip()
            except Exception as e:
                print(f"OCR Error: {e}")
                return ""
    
    def parse_plus_result(self, text: str) -> ParseResult:
        """
        Parse plus upgrade result from log text.
        
        Args:
            text: OCR extracted text
            
        Returns:
            ParseResult with plus level or failure status
        """
        with self._ocr_lock:
            # Check for failure first
            if self.FAILED_PATTERN.search(text):
                return ParseResult(
                    success=True,
                    result_type="failed",
                    raw_text=text
                )
            
            # Look for plus pattern: +1, +2, etc.
            match = self.PLUS_PATTERN.search(text)
            if match:
                plus_level = int(match.group(1))
                return ParseResult(
                    success=True,
                    result_type="plus",
                    value=plus_level,
                    raw_text=text
                )
            
            # Try alternative plus patterns
            alt_match = self.PLUS_ALT_PATTERN.search(text)
            if alt_match:
                # Check which group matched
                for group in alt_match.groups():
                    if group:
                        plus_level = int(group)
                        return ParseResult(
                            success=True,
                            result_type="plus",
                            value=plus_level,
                            raw_text=text
                        )
            
            # Check for success indicator (might show plus level)
            if self.SUCCESS_PATTERN.search(text):
                # Try to find any number that might be the plus level
                numbers = re.findall(r'\b(\d+)\b', text)
                for num in numbers:
                    level = int(num)
                    if 1 <= level <= 20:  # Reasonable plus level range
                        return ParseResult(
                            success=True,
                            result_type="plus",
                            value=level,
                            raw_text=text
                        )
            
            # Unknown result
            return ParseResult(
                success=False,
                result_type="unknown",
                raw_text=text,
                error="Could not parse plus result"
            )
    
    def parse_stat_result(self, text: str) -> ParseResult:
        """
        Parse stat upgrade result from log text.
        Handles formats:
        - [12.2->12.4]
        - [(82.9%~98.6%) -> (81.6%~97.1%)]
        - beenchangedto(297->301]
        - Any text with number->number pattern
        
        Args:
            text: OCR extracted text
            
        Returns:
            ParseResult with stat values
        """
        with self._ocr_lock:
            # Try SRO specific "changedto" pattern first
            changedto_match = self.STAT_CHANGEDTO_PATTERN.search(text)
            if changedto_match:
                try:
                    old_value = float(changedto_match.group(1))
                    new_value = float(changedto_match.group(2))
                    
                    return ParseResult(
                        success=True,
                        result_type="stat",
                        value={
                            'old_value': old_value,
                            'new_value': new_value,
                            'improved': new_value > old_value
                        },
                        raw_text=text
                    )
                except (ValueError, IndexError):
                    pass
            
            # Try parens pattern: (297->301]
            parens_match = self.STAT_PARENS_PATTERN.search(text)
            if parens_match:
                try:
                    old_value = float(parens_match.group(1))
                    new_value = float(parens_match.group(2))
                    
                    return ParseResult(
                        success=True,
                        result_type="stat",
                        value={
                            'old_value': old_value,
                            'new_value': new_value,
                            'improved': new_value > old_value
                        },
                        raw_text=text
                    )
                except (ValueError, IndexError):
                    pass
            
            # Try range pattern: [(82.9%~98.6%) -> (81.6%~97.1%)]
            range_match = self.STAT_RANGE_PATTERN.search(text)
            if range_match:
                groups = range_match.groups()
                try:
                    old_min = float(groups[0])
                    old_max = float(groups[1])
                    new_min = float(groups[2])
                    new_max = float(groups[3])
                    
                    # Calculate average values for comparison
                    old_avg = (old_min + old_max) / 2
                    new_avg = (new_min + new_max) / 2
                    
                    return ParseResult(
                        success=True,
                        result_type="stat",
                        value={
                            'old_range': (old_min, old_max),
                            'new_range': (new_min, new_max),
                            'old_avg': old_avg,
                            'new_avg': new_avg,
                            'improved': new_avg > old_avg
                        },
                        raw_text=text
                    )
                except (ValueError, IndexError):
                    pass
            
            # Try simple pattern: [12.2->12.4]
            simple_match = self.STAT_SIMPLE_PATTERN.search(text)
            if simple_match:
                try:
                    old_value = float(simple_match.group(1))
                    new_value = float(simple_match.group(2))
                    
                    return ParseResult(
                        success=True,
                        result_type="stat",
                        value={
                            'old_value': old_value,
                            'new_value': new_value,
                            'improved': new_value > old_value
                        },
                        raw_text=text
                    )
                except ValueError:
                    pass
            
            # Try generic arrow pattern: number->number
            arrow_matches = self.STAT_ARROW_PATTERN.findall(text)
            if arrow_matches:
                try:
                    # Use the last match (most recent)
                    old_val, new_val = arrow_matches[-1]
                    old_value = float(old_val)
                    new_value = float(new_val)
                    
                    return ParseResult(
                        success=True,
                        result_type="stat",
                        value={
                            'old_value': old_value,
                            'new_value': new_value,
                            'improved': new_value > old_value
                        },
                        raw_text=text
                    )
                except (ValueError, IndexError):
                    pass
            
            # Check for failure
            if self.FAILED_PATTERN.search(text):
                return ParseResult(
                    success=True,
                    result_type="failed",
                    raw_text=text
                )
            
            # Unknown result
            return ParseResult(
                success=False,
                result_type="unknown",
                raw_text=text,
                error="Could not parse stat result"
            )
    
    def process_log_region(
        self, 
        image: np.ndarray, 
        mode: str = "plus",
        threshold: int = 150,
        psm: int = 6
    ) -> ParseResult:
        """
        Process a log region image and parse the result.
        
        Args:
            image: BGR numpy array of log region
            mode: "plus" or "stat" mode
            threshold: Threshold for preprocessing
            psm: Tesseract PSM mode
            
        Returns:
            ParseResult with parsed data
        """
        with self._ocr_lock:
            # Extract text
            text = self.extract_text(image, psm, threshold)
            
            if not text:
                return ParseResult(
                    success=False,
                    result_type="unknown",
                    error="No text extracted"
                )
            
            # Parse based on mode
            if mode == "plus":
                return self.parse_plus_result(text)
            elif mode == "stat":
                return self.parse_stat_result(text)
            else:
                return ParseResult(
                    success=False,
                    result_type="unknown",
                    error=f"Unknown mode: {mode}"
                )
    
    def debug_save_preprocessed(self, image: np.ndarray, filepath: str, threshold: int = 150) -> None:
        """
        Save preprocessed image for debugging OCR issues.
        
        Args:
            image: BGR numpy array
            filepath: Path to save image
            threshold: Threshold value
        """
        processed = self.preprocess_image(image, threshold)
        cv2.imwrite(filepath, processed)


# Global instance
ocr_processor = OCRProcessor()
